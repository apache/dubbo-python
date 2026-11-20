# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

import asyncio
import ssl
import time
from collections import deque
from collections.abc import Callable
from typing import Any, cast

import anyio
import ngh2

from dubbo.constants import (
    CONNECTION_INITIAL_WINDOW_SIZE_KEY,
    DEFAULT_CONNECTION_INITIAL_WINDOW_SIZE,
    DEFAULT_INITIAL_WINDOW_SIZE,
    DEFAULT_KEEP_ALIVE_TIMEOUT,
    DEFAULT_MAX_CONCURRENT_STREAMS,
    DEFAULT_MAX_HEADER_LIST_SIZE,
    INITIAL_WINDOW_SIZE_KEY,
    KEEP_ALIVE_INTERVAL_KEY,
    KEEP_ALIVE_TIMEOUT_KEY,
    MAX_CONCURRENT_STREAMS_KEY,
    MAX_HEADER_LIST_SIZE_KEY,
)
from dubbo.transport.h2.base import H2ErrorCode, H2Headers
from dubbo.transport.h2.exceptions import H2ConnectionError, H2Error, H2StreamError, H2StreamResetError
from dubbo.url import URL
from dubbo.utils import close_then_abort
from dubbo.utils.converters import milliseconds
from dubbo.utils.net import format_address

from .bdp import BDP_PING, BdpEstimator
from .keep_alive import KeepAlive
from .stream import AioH2Stream

__all__ = ["AioH2Connection"]

_READ_BUFFER_SIZE = 64 * 1024
_WRITE_CHUNK_SIZE = 64 * 1024
# The connection window every HTTP/2 connection starts with.
_PROTOCOL_CONNECTION_WINDOW_SIZE = 64 * 1024 - 1
_STREAM_SEND_BUFFER_SIZE_KEY = "stream-send-buffer-size"
_HTTP2_TLS_VERSIONS = frozenset({"TLSv1.2", "TLSv1.3"})
_DEFAULT_STREAM_SEND_BUFFER_SIZE = 256 * 1024


class AioH2Connection(asyncio.BufferedProtocol):
    """Runs one ngh2 engine over an asyncio transport.

    asyncio invokes every transport callback synchronously on one event loop,
    so engine state needs no mutex; events and futures only suspend tasks until that
    state changes. A change wakes only the tasks it concerns: a stream's own
    receiver or sender, the senders waiting for output to drain, or the tasks
    waiting to open a stream. Output is batched within a loop iteration and
    written in bounded chunks, with one early client flush when a request
    ends.

    Streams queue frames through the stream operations below and keep their
    own state; the connection hands them what arrives through their ``_on_*``
    methods. The client or server that owns the connection uses the lifecycle
    methods. The HTTP/2 parameters of ``url`` configure it as `H2Client`
    describes them, and ``stream-send-buffer-size`` as `AioH2Client`
    describes it.
    """

    def __init__(
        self,
        role: ngh2.Role,
        url: URL,
        *,
        require_h2_alpn: bool = False,
        on_connected: Callable[["AioH2Connection"], None] | None = None,
        on_stream: Callable[[AioH2Stream], None] | None = None,
        on_closed: Callable[["AioH2Connection"], None] | None = None,
    ) -> None:
        self.is_server = role is ngh2.Role.SERVER
        max_streams = url.get_parameter(MAX_CONCURRENT_STREAMS_KEY, int, DEFAULT_MAX_CONCURRENT_STREAMS)
        max_header_list = url.get_parameter(MAX_HEADER_LIST_SIZE_KEY, int, DEFAULT_MAX_HEADER_LIST_SIZE)
        fixed_stream_window = url.get_parameter(INITIAL_WINDOW_SIZE_KEY, int, None)
        stream_window = DEFAULT_INITIAL_WINDOW_SIZE if fixed_stream_window is None else fixed_stream_window
        connection_window = url.get_parameter(
            CONNECTION_INITIAL_WINDOW_SIZE_KEY, int, DEFAULT_CONNECTION_INITIAL_WINDOW_SIZE
        )
        self._keep_alive_interval = url.get_parameter(KEEP_ALIVE_INTERVAL_KEY, milliseconds, None)
        self._keep_alive_timeout = url.get_parameter(KEEP_ALIVE_TIMEOUT_KEY, milliseconds, DEFAULT_KEEP_ALIVE_TIMEOUT)
        self._send_buffer_size = url.get_parameter(_STREAM_SEND_BUFFER_SIZE_KEY, int, _DEFAULT_STREAM_SEND_BUFFER_SIZE)
        if self._send_buffer_size <= 0:
            raise ValueError(f"URL parameter {_STREAM_SEND_BUFFER_SIZE_KEY!r} must be positive")

        # ngh2 checks each value against HTTP/2 when it takes it.
        self._engine = ngh2.Connection(
            role,
            ngh2.Configuration(
                auto_window_update=False,
                initial_peer_max_concurrent_streams=max_streams,
                max_inbound_header_list_size=max_header_list,
            ),
        )
        settings = {
            ngh2.Setting.MAX_CONCURRENT_STREAMS: max_streams,
            ngh2.Setting.INITIAL_WINDOW_SIZE: stream_window,
            ngh2.Setting.MAX_HEADER_LIST_SIZE: max_header_list,
        }
        if role is ngh2.Role.CLIENT:
            settings[ngh2.Setting.ENABLE_PUSH] = 0
        self._engine.initiate_connection(settings)
        if connection_window != _PROTOCOL_CONNECTION_WINDOW_SIZE:
            self._engine.set_local_window_size(connection_window)

        self._require_h2_alpn = require_h2_alpn
        self._on_connected = on_connected
        self._on_stream = on_stream
        self._on_closed = on_closed

        self._buffer = bytearray(_READ_BUFFER_SIZE)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._transport: asyncio.Transport | None = None
        self.peer: str | None = None
        self._write_paused = False
        self._flush_scheduled = False
        # Whether a request has gone out ahead of the flush that ends this loop iteration.
        self._wrote_ahead = False
        # Whether frames were queued since output was last written.
        self._queued = False
        self._writing = False
        self._transport_closed = False
        self._transport_lost = anyio.Event()
        # Set by the first SETTINGS of the peer, which ends its connection preface, or by the end of the connection.
        self._preface_ended = anyio.Event()
        self._keep_alive: KeepAlive | None = None
        self._bdp = BdpEstimator(stream_window) if fixed_stream_window is None else None

        # On a client, which refuses server push, every tracked stream is one it opened.
        self._streams_by_id: dict[int, AioH2Stream] = {}
        # Assumed until the first SETTINGS of the peer, which a client waits for before opening streams.
        self._peer_max_concurrent_streams = max_streams
        # Streams waiting for output to drain or for asyncio to resume writing.
        self._blocked_senders: set[AioH2Stream] = set()
        # The tasks waiting to open a stream, in arrival order, each told whether it may; asyncio futures, as this
        # is on the path of every call when the streams run out.
        self._stream_waiters: deque[asyncio.Future[bool]] = deque()
        # The streams set aside for waiters that have been told and not yet opened theirs.
        self._granted_streams = 0

        self._draining = False
        self._goaway_error_code: int | None = None
        self._goaway_last_stream_id: int | None = None
        self._closing = False
        self._engine_terminated = False
        self._failure: H2ConnectionError | None = None

        self._event_handlers: dict[type[ngh2.Event], Callable[[Any], None]] = {
            ngh2.RequestReceived: self._handle_request_received,
            ngh2.ResponseReceived: self._handle_response_received,
            ngh2.DataReceived: self._handle_data_received,
            ngh2.TrailersReceived: self._handle_trailers_received,
            ngh2.StreamReset: self._handle_stream_reset,
            ngh2.StreamClosed: self._handle_stream_closed,
            ngh2.SettingsReceived: self._handle_settings_received,
            ngh2.PingAcknowledged: self._handle_ping_acknowledged,
            ngh2.GoAwayReceived: self._handle_goaway_received,
            ngh2.ConnectionClosed: self._handle_connection_closed,
        }

    @property
    def closed(self) -> bool:
        """Return whether asyncio has reported transport closure."""
        return self._transport_closed

    @property
    def accepting_streams(self) -> bool:
        """Return whether this connection can still initiate a stream."""
        return (
            self._transport is not None
            and not self._transport_closed
            and not self._closing
            and self._failure is None
            and not self._draining
            and self._engine.can_send_request
        )

    async def open_stream(self, headers: H2Headers, *, end_stream: bool) -> AioH2Stream | None:
        """Open a local stream, or return ``None`` when the connection can no longer open one."""
        if not await self._wait_for_stream():
            return None

        try:
            stream_id = self._engine.send_request(headers, end_stream=end_stream)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error) from error

        stream = AioH2Stream(self, stream_id, headers_sent=True, send_ended=end_stream)
        self._streams_by_id[stream_id] = stream
        self._schedule_flush(request_ended=end_stream)

        try:
            await self.wait_writable(stream)
        except BaseException:
            stream._reset_after_cancel()
            raise

        return stream

    def raise_if_failed(self) -> None:
        """Raise the first connection failure, or an error if the connection is closed."""
        if self._failure is not None:
            raise self._failure
        if self._transport_closed:
            raise H2ConnectionError("the HTTP/2 connection is closed")

    # Stream operations. Each queues frames and leaves them to the next flush.

    def send_response(self, stream_id: int, headers: H2Headers, *, end_stream: bool) -> None:
        try:
            self._engine.send_response(stream_id, headers, end_stream=end_stream)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error, stream_id) from error

        self._schedule_flush()

    def send_data(self, stream_id: int, data: bytes, *, end_stream: bool) -> None:
        try:
            self._engine.send_data(stream_id, data, end_stream=end_stream)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error, stream_id) from error

        self._schedule_flush(request_ended=end_stream)

    def send_trailers(self, stream_id: int, trailers: H2Headers) -> None:
        try:
            self._engine.send_trailers(stream_id, trailers)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error, stream_id) from error

        self._schedule_flush()

    def end_stream(self, stream_id: int) -> None:
        try:
            self._engine.end_stream(stream_id)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error, stream_id) from error

        self._schedule_flush(request_ended=True)

    def reset_stream(self, stream_id: int, error_code: int, *, after_end_stream: bool = False) -> None:
        """Reset a stream; with ``after_end_stream``, once the frames queued for it are written."""
        try:
            self._engine.reset_stream(stream_id, error_code, after_end_stream=after_end_stream)
        except ngh2.NGH2Error as error:
            raise _map_ngh2_error(error, stream_id) from error

        self._schedule_flush()

    def consume(self, stream_id: int, amount: int) -> None:
        """Return receive-window credit for bytes the application read or dropped."""
        if not amount or self._transport_closed or self._engine_terminated:
            return

        try:
            self._return_credit(stream_id, amount)
        except ngh2.NGH2Error as error:
            failure = _connection_error(error)
            self._fail_connection(failure)
            raise failure from error

        self._schedule_flush()

    async def wait_writable(self, stream: AioH2Stream) -> None:
        """Wait until asyncio accepts writes and at most a send buffer of the stream's body is queued."""
        while True:
            stream._raise_if_send_failed()
            if not self._write_paused and self._engine.queued_body_size(stream.stream_id) <= self._send_buffer_size:
                return

            self._blocked_senders.add(stream)
            try:
                await stream._wait_to_send()
            finally:
                self._blocked_senders.discard(stream)

    def announce_shutdown(self) -> None:
        """Ask the peer to open no more streams, the first step of a graceful close."""
        if self._transport is None or self._closing or self._transport_closed or self._engine_terminated:
            return

        try:
            self._engine.send_shutdown_notice()
        except ngh2.NGH2Error as error:
            self._fail_connection(_connection_error(error))
            self.abort()
            return

        self._schedule_flush()

    async def aclose(self) -> None:
        """Close once the open streams finish and the peer has read the output, waiting up to a grace period; abort after it or when cancelled."""
        self.start_close()
        if self._transport is None:
            self.abandon()
            return

        await close_then_abort(self.wait_closed, lambda: self._transport_closed, self.abort)

    def start_close(self) -> None:
        """Send the final GOAWAY, without waiting for the socket to close.

        Open streams keep sending what they queued; once they finish, the
        engine reports ConnectionClosed and the flush closes the socket.
        """
        if self._transport_closed or self._closing:
            return

        self._closing = True
        self._stop_keep_alive()
        self._bdp = None
        self._notify_capacity()

        if not self._engine_terminated:
            try:
                self._engine.send_goaway()
            except ngh2.NGH2Error as error:
                self._fail_connection(_connection_error(error))
            else:
                self._write_outbound()
                return

        if self._transport is not None and not self._transport.is_closing():
            self._transport.close()

    def abort(self) -> None:
        """Abort the socket, as when graceful shutdown takes too long."""
        self._closing = True
        self._stop_keep_alive()
        if self._transport is None:
            self.connection_lost(None)
            return

        self._transport.abort()

    def abandon(self) -> None:
        """Finish a connection whose transport was never created."""
        self.start_close()
        if self._transport is None:
            self.connection_lost(None)

    async def wait_established(self) -> None:
        """Wait for the first SETTINGS of the peer, which shows that an HTTP/2 endpoint answers.

        Raises:
            H2ConnectionError: The connection failed or closed first.
        """
        await self._preface_ended.wait()
        self.raise_if_failed()

    async def wait_closed(self) -> None:
        """Wait until asyncio reports that the socket transport is lost."""
        if not self._transport_closed:
            await self._transport_lost.wait()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Attach the socket transport and send the pending connection preface."""
        socket_transport = cast(asyncio.Transport, transport)
        self._loop = asyncio.get_running_loop()
        self._transport = socket_transport
        self.peer = _address(socket_transport.get_extra_info("peername"))
        if self._transport_closed or self._closing:
            socket_transport.close()
            return

        if self._require_h2_alpn:
            problem = _tls_problem(socket_transport.get_extra_info("ssl_object"))
            if problem is not None:
                self._fail_connection(H2ConnectionError(problem))
                self.abort()
                return

        if self._on_connected is not None:
            self._on_connected(self)
        if self._closing or self._transport_closed:
            return

        self._write_outbound()
        if self._keep_alive_interval is not None:
            self._keep_alive = KeepAlive(
                self._loop,
                interval=self._keep_alive_interval,
                timeout=self._keep_alive_timeout,
                ping=self._send_ping,
                expire=self._keep_alive_expired,
            )

    def get_buffer(self, sizehint: int) -> memoryview:
        """Return the reusable buffer used by asyncio's buffered protocol API."""
        return memoryview(self._buffer)

    def buffer_updated(self, nbytes: int) -> None:
        """Feed the newly filled receive-buffer prefix into ngh2."""
        if self._transport_closed:
            return

        try:
            self._engine.receive_data(memoryview(self._buffer)[:nbytes])
            if self._keep_alive is not None:
                # Socket activity counts even when an extension frame emits no event.
                self._keep_alive.received()
            self._dispatch_events(self._engine.events())
            self._schedule_flush()
        except ngh2.NGH2Error as error:
            self._fail_connection(_connection_error(error))
            self.abort()

    def pause_writing(self) -> None:
        """Record asyncio write backpressure."""
        self._write_paused = True

    def resume_writing(self) -> None:
        """Resume engine output after asyncio releases write backpressure."""
        self._write_paused = False
        self._write_outbound()
        self._wake_senders()

    def connection_lost(self, exc: Exception | None) -> None:
        """Finalize transport loss and fail streams that did not complete."""
        if self._transport_closed:
            return

        self._stop_keep_alive()
        self._transport_closed = True
        self._preface_ended.set()
        if any(not stream._finished for stream in self._streams_by_id.values()):
            if exc is None:
                failure = H2ConnectionError("the HTTP/2 connection closed before its streams completed")
            else:
                failure = H2ConnectionError(f"the HTTP/2 connection failed: {exc}")
            self._fail_connection(failure)

        self._wake_all()
        # Streams a caller still holds keep their own buffers, not their siblings.
        self._streams_by_id.clear()
        self._transport_lost.set()
        if self._on_closed is not None:
            self._on_closed(self)

    def _schedule_flush(self, *, request_ended: bool = False) -> None:
        """Flush later in this loop iteration, so output from every stream shares one write.

        A client with other calls open writes at once when the first request
        of an iteration ends while asyncio holds none of its output unsent,
        so that the server starts on that request while the rest gathers.
        """
        if self._loop is None:
            return

        self._queued = True
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self._loop.call_soon(self._flush_outbound)
        # One write ahead per iteration; the other output still shares the flush.
        transport = self._transport
        if (
            request_ended
            and not self.is_server
            and not self._wrote_ahead
            and len(self._streams_by_id) > 1  # A lone call has nothing to overlap with.
            and not self._writing
            and transport is not None
            and not transport.get_write_buffer_size()  # Queued output would not arrive sooner.
        ):
            self._wrote_ahead = True
            self._write_outbound()

    def _flush_outbound(self) -> None:
        """End the loop iteration's batch, writing what was queued since output was last written."""
        self._flush_scheduled = self._wrote_ahead = False
        if self._queued:
            self._write_outbound()

    def _write_outbound(self) -> None:
        """Write available engine output until empty or asyncio applies backpressure."""
        self._queued = False
        transport = self._transport
        # Closing an asyncio SSL transport twice detaches it, so a later abort() is lost.
        if transport is None or transport.is_closing() or self._write_paused:
            return

        wrote_data = False
        self._writing = True
        try:
            while not self._write_paused:
                # Bound engine allocations so asyncio can apply backpressure between writes.
                outgoing = self._engine.data_to_send(_WRITE_CHUNK_SIZE)
                # Producing output may itself complete streams and emit events.
                self._dispatch_events(self._engine.events())
                if outgoing:
                    transport.write(outgoing)
                    wrote_data = True
                    bdp = self._bdp
                    if bdp is not None and bdp.probe_unwritten and self._loop is not None:
                        # The engine writes a queued PING ahead of DATA, so this write carries it.
                        bdp.probe_written(time.perf_counter())
                if self._engine_terminated:
                    transport.close()
                    break
                if not outgoing:
                    break
        except ngh2.NGH2Error as error:
            self._fail_connection(_connection_error(error))
            self.abort()
        finally:
            self._writing = False
            if wrote_data:
                self._wake_senders()

    def _dispatch_events(self, events: list[ngh2.Event]) -> None:
        """Apply engine events in order; streams wake their own waiters."""
        for event in events:
            handler = self._event_handlers.get(type(event))
            if handler is not None:
                handler(event)

    def _handle_request_received(self, event: ngh2.RequestReceived) -> None:
        stream = AioH2Stream(
            self,
            event.stream_id,
            headers_sent=False,
            headers=event.headers,
            receive_ended=event.end_stream,
        )
        self._streams_by_id[event.stream_id] = stream
        if self._on_stream is not None:
            self._on_stream(stream)

    def _handle_response_received(self, event: ngh2.ResponseReceived) -> None:
        stream = self._streams_by_id.get(event.stream_id)
        if stream is not None:
            stream._on_headers(event.headers, end_stream=event.end_stream)

    def _handle_data_received(self, event: ngh2.DataReceived) -> None:
        if self._bdp is not None:
            self._bdp.data_received = True

        stream = self._streams_by_id.get(event.stream_id)
        if stream is not None and not stream._released:
            stream._on_data(event.data, end_stream=event.end_stream)
            return

        # DATA that nothing will read still occupies flow-control credit.
        if event.data:
            self._return_credit(event.stream_id, len(event.data))

    def _handle_trailers_received(self, event: ngh2.TrailersReceived) -> None:
        stream = self._streams_by_id.get(event.stream_id)
        if stream is not None:
            stream._on_trailers(event.headers)

    def _handle_stream_reset(self, event: ngh2.StreamReset) -> None:
        stream = self._streams_by_id.get(event.stream_id)
        if stream is None:
            return

        error = H2StreamResetError(event.stream_id, event.error_code)
        # RFC 9113 section 8.1: after a complete response, NO_ERROR only stops the request.
        if event.error_code == H2ErrorCode.NO_ERROR and stream._receive_ended:
            stream._stop_sending(error)
            return

        self._drop_unread(stream)
        stream._abort(error)

    def _handle_stream_closed(self, event: ngh2.StreamClosed) -> None:
        stream = self._streams_by_id.pop(event.stream_id, None)
        if stream is None:
            return

        self._notify_capacity()

        if event.local_error is None and not event.error_code:
            stream._on_closed()
            return

        self._drop_unread(stream)
        # A GOAWAY refuses the streams above its last stream ID unprocessed; RFC 9113 section 6.8.
        refused = (
            event.error_code == H2ErrorCode.REFUSED_STREAM
            and self._goaway_last_stream_id is not None
            and event.stream_id > self._goaway_last_stream_id
        )
        if refused or isinstance(event.local_error, ngh2.ConnectionClosingError):
            message = str(event.local_error or "") or "the HTTP/2 connection is draining"
            failure: H2Error = H2ConnectionError(
                message,
                error_code=self._goaway_error_code,
                last_stream_id=self._goaway_last_stream_id,
            )
        else:
            message = (
                str(event.local_error)
                if event.local_error is not None
                else f"the HTTP/2 stream closed with error code {event.error_code}"
            )
            failure = H2StreamError(message, stream_id=event.stream_id)
        stream._fail(failure)

    def _handle_settings_received(self, event: ngh2.SettingsReceived) -> None:
        self._preface_ended.set()
        # The engine holds the limit in force, unlimited when the first SETTINGS leaves it out.
        maximum = self._engine.remote_settings[ngh2.Setting.MAX_CONCURRENT_STREAMS]
        if maximum != self._peer_max_concurrent_streams:
            self._peer_max_concurrent_streams = maximum
            self._notify_capacity()

    def _handle_ping_acknowledged(self, event: ngh2.PingAcknowledged) -> None:
        bdp = self._bdp
        if event.opaque_data == BDP_PING and bdp is not None and self._loop is not None:
            # A round trip on loopback is shorter than a tick of the loop clock on Windows before Python 3.13.
            window = bdp.probe_acknowledged(time.perf_counter())
            if bdp.finished:
                self._bdp = None
            if window is None:
                return

            try:
                # The peer applies it to every open stream; RFC 9113 section 6.9.2.
                self._engine.update_settings({ngh2.Setting.INITIAL_WINDOW_SIZE: window})
            except ngh2.ConnectionStateError:
                # A connection that is shutting down keeps the windows it has.
                self._bdp = None
            return

        if self._keep_alive is not None:
            self._keep_alive.acknowledged(event.opaque_data)

    def _handle_goaway_received(self, event: ngh2.GoAwayReceived) -> None:
        self._draining = True
        self._bdp = None
        self._goaway_error_code = event.error_code
        self._goaway_last_stream_id = event.last_stream_id
        self._notify_capacity()

    def _handle_connection_closed(self, event: ngh2.ConnectionClosed) -> None:
        # The flush that produced this event writes its output first, then closes the socket.
        self._engine_terminated = True
        self._notify_capacity()
        if event.error_code:
            self._fail_connection(
                H2ConnectionError(
                    "peer closed the HTTP/2 connection",
                    error_code=event.error_code,
                    last_stream_id=self._goaway_last_stream_id,
                )
            )

    def _drop_unread(self, stream: AioH2Stream) -> None:
        """Drop a stream's unread input and return its connection credit; engine failures propagate."""
        amount = stream._drop_unread()
        if amount and not self._transport_closed and not self._engine_terminated:
            self._return_credit(stream.stream_id, amount)

    def _return_credit(self, stream_id: int, amount: int) -> None:
        """Return receive-window credit, and start a BDP probe when the estimator asks; engine failures propagate."""
        self._engine.consume_received_data(stream_id, amount)

        bdp = self._bdp
        if bdp is None or not bdp.credit_returned(amount):
            return

        try:
            self._engine.send_ping(BDP_PING)
        except ngh2.ConnectionStateError:
            # A connection that is shutting down keeps the windows it has.
            self._bdp = None

    async def _wait_for_stream(self) -> bool:
        """Wait in arrival order for room for one more stream; return ``False`` once the connection opens no more."""
        first = False
        while self.accepting_streams:
            if first:
                # The waiters told after this one wake after it, so the streams set aside for them come second.
                ready = self._free_streams() + self._granted_streams > 0
            else:
                # Nobody passes those already waiting.
                ready = not self._stream_waiters and self._free_streams() > 0
            if ready:
                return True

            waiter = asyncio.get_running_loop().create_future()
            if first:
                self._stream_waiters.appendleft(waiter)
            else:
                self._stream_waiters.append(waiter)
            try:
                allowed = await waiter
            except BaseException:
                if not waiter.done() or waiter.cancelled():
                    waiter.cancel()
                    # A cancelled waiter may already have been passed over.
                    if waiter in self._stream_waiters:
                        self._stream_waiters.remove(waiter)
                elif waiter.result():
                    # The stream set aside goes to the next waiter.
                    self._granted_streams -= 1
                    self._notify_capacity()
                raise

            if not allowed:
                return False
            self._granted_streams -= 1
            # Should the peer have lowered its limit meanwhile, it waits again ahead of the others.
            first = True

        return False

    def _free_streams(self) -> int:
        return self._peer_max_concurrent_streams - len(self._streams_by_id) - self._granted_streams

    def _notify_capacity(self) -> None:
        """Set aside the free streams for the waiters in arrival order, or tell them all the connection opens no more."""
        waiters = self._stream_waiters
        if not self.accepting_streams:
            while waiters:
                waiter = waiters.popleft()
                if not waiter.done():
                    waiter.set_result(False)
            return

        free = self._free_streams()
        while waiters and free > 0:
            waiter = waiters.popleft()
            # A cancelled waiter is passed over; it takes nothing.
            if not waiter.done():
                waiter.set_result(True)
                self._granted_streams += 1
                free -= 1

    def _wake_senders(self) -> None:
        for stream in self._blocked_senders:
            stream._wake_sender()

    def _wake_all(self) -> None:
        """Wake every waiter after a connection-wide change, such as failure or closure."""
        for stream in tuple(self._streams_by_id.values()):
            stream._wake()
        self._wake_senders()
        self._notify_capacity()

    def _fail_connection(self, error: H2ConnectionError) -> None:
        """Preserve the first failure and propagate it to active streams."""
        self._stop_keep_alive()
        if self._failure is None:
            self._failure = error
        for stream in tuple(self._streams_by_id.values()):
            stream._abort(self._failure)
        self._preface_ended.set()
        self._wake_all()

    def _send_ping(self, payload: bytes) -> None:
        try:
            self._engine.send_ping(payload)
        except ngh2.NGH2Error as error:
            self._fail_connection(_connection_error(error))
            self.abort()
            return

        self._schedule_flush()

    def _keep_alive_expired(self) -> None:
        if self._closing or self._transport_closed:
            return

        self._fail_connection(H2ConnectionError("the HTTP/2 keep-alive PING acknowledgement timed out"))
        self.abort()

    def _stop_keep_alive(self) -> None:
        if self._keep_alive is not None:
            self._keep_alive.stop()


def _map_ngh2_error(error: ngh2.NGH2Error, stream_id: int | None = None) -> H2Error:
    """Translate engine failures into dependency-independent transport errors."""
    message = str(error) or type(error).__name__
    if stream_id is not None and isinstance(error, (ngh2.StreamStateError, ngh2.StreamProtocolError)):
        return H2StreamError(message, stream_id=stream_id)
    return H2ConnectionError(message)


def _address(peername: Any) -> str | None:
    """Return a socket address as ``host:port``, with an IPv6 host in brackets."""
    return format_address(*peername[:2]) if isinstance(peername, tuple) else None


def _connection_error(error: ngh2.NGH2Error) -> H2ConnectionError:
    return cast(H2ConnectionError, _map_ngh2_error(error))


def _tls_problem(ssl_object: ssl.SSLObject | None) -> str | None:
    """Say how a TLS session breaks what RFC 9113 section 9.2 requires of HTTP/2, if it does."""
    if ssl_object is None or ssl_object.selected_alpn_protocol() != "h2":
        return "TLS did not negotiate the 'h2' ALPN protocol"
    if ssl_object.version() not in _HTTP2_TLS_VERSIONS:
        return f"TLS negotiated {ssl_object.version()}, below the TLSv1.2 that HTTP/2 requires"
    if ssl_object.compression() is not None:
        return "TLS negotiated compression, which HTTP/2 forbids"
    return None
