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

"""A TCP connection that carries Dubbo frames.

It is an asyncio protocol: the I/O layer that AnyIO does not cover.
"""

import asyncio
import itertools
import logging
import struct
from collections.abc import Callable
from typing import Any, Self, cast

import anyio
import attrs

from dubbo.constants import (
    CONNECT_TIMEOUT_KEY,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_HEARTBEAT,
    DEFAULT_PAYLOAD,
    HEARTBEAT_KEY,
    HEARTBEAT_TIMEOUT_KEY,
    PAYLOAD_KEY,
)
from dubbo.serialization import JavaSerialization
from dubbo.transport.tls import TLS_KEYS
from dubbo.url import SSL_CONTEXT, URL
from dubbo.utils import close_then_abort
from dubbo.utils.converters import milliseconds
from dubbo.utils.net import format_address

__all__ = [
    "FLAG_REQUEST",
    "FLAG_TWO_WAY",
    "SERIALIZATION_MASK",
    "ConnectionSettings",
    "DubboConnection",
    "EventBodies",
    "next_request_id",
]

_logger = logging.getLogger(__name__)

_MAGIC = 0xDABB
# Magic, flags with the serialization id, status, request id and body length.
_HEADER = struct.Struct(">HBBqI")
FLAG_REQUEST = 0x80
FLAG_TWO_WAY = 0x40
_FLAG_EVENT = 0x20
SERIALIZATION_MASK = 0x1F  # The bits of the flags that hold the serialization id.
_OK = 20
_READONLY = "R"  # The event data that tells consumers a provider stops taking calls.
_WRITABLE = "W"  # The event data that tells consumers a provider takes calls again.
_READ_SIZE = 64 * 1024  # Bytes the read buffer keeps free for each read.

# The id of each request a process sends, unique among all its connections.
next_request_id = itertools.count(1).__next__

# Called with the connection, the flags with the serialization id, the status, the request id and the body.
_FrameHandler = Callable[["DubboConnection", int, int, int, bytes], None]


@attrs.define(frozen=True, kw_only=True)
class ConnectionSettings:
    """How the connections of a consumer or a provider behave, from the parameters of its URL.

    Attributes:
        connect_timeout: Seconds a consumer waits for a connection, its TLS
            handshake included, from ``connect-timeout`` in milliseconds; 3
            when absent.
        heartbeat: Seconds of silence before a consumer sends a heartbeat,
            from ``heartbeat`` in milliseconds; 60 when absent.
        idle_timeout: Seconds without reading before a connection closes,
            from ``heartbeat.timeout`` in milliseconds; three heartbeats when
            absent.
        max_body: Bytes of the largest body, from ``payload``; 8 MiB when
            absent.
        tls: The TLS parameters and context of the URL, as
            `dubbo.transport.tls.get_ssl_context` reads them; connections of
            other TLS share no client or server.
    """

    connect_timeout: float
    heartbeat: float
    idle_timeout: float
    max_body: int
    tls: tuple[Any, ...]

    @classmethod
    def from_url(cls, url: URL) -> Self:
        """Return the settings ``url`` gives.

        Raises:
            ValueError: A setting is not a positive number, or the idle
                timeout is shorter than two heartbeats.
        """
        connect_timeout = url.get_parameter(CONNECT_TIMEOUT_KEY, milliseconds, DEFAULT_CONNECT_TIMEOUT)
        heartbeat = url.get_parameter(HEARTBEAT_KEY, milliseconds, DEFAULT_HEARTBEAT)
        idle_timeout = url.get_parameter(HEARTBEAT_TIMEOUT_KEY, milliseconds, 3 * heartbeat)
        max_body = url.get_parameter(PAYLOAD_KEY, int, DEFAULT_PAYLOAD)
        if connect_timeout <= 0 or heartbeat <= 0 or max_body <= 0:
            raise ValueError(f"{CONNECT_TIMEOUT_KEY}, {HEARTBEAT_KEY} and {PAYLOAD_KEY} must be positive")
        if idle_timeout < 2 * heartbeat:
            raise ValueError(f"{HEARTBEAT_TIMEOUT_KEY} must be at least two heartbeats")

        tls = (*(url.parameters.get(key) for key in TLS_KEYS), url.attributes.get(SSL_CONTEXT))
        return cls(
            connect_timeout=connect_timeout,
            heartbeat=heartbeat,
            idle_timeout=idle_timeout,
            max_body=max_body,
            tls=tls,
        )


@attrs.define(frozen=True, kw_only=True)
class EventBodies:
    """The bodies of the events a connection sends, serialized once, and how it reads those it receives.

    Attributes:
        heartbeat: A heartbeat, a serialized null.
        readonly: The notice that a provider stops taking calls.
        read: Returns the value an event body holds; raises `ValueError`
            for a body that holds none.
    """

    heartbeat: bytes
    readonly: bytes
    read: Callable[[bytes], Any]

    @classmethod
    def from_serialization(cls, serialization: JavaSerialization) -> Self:
        """Return the bodies ``serialization`` writes and reads."""
        return cls(
            heartbeat=serialization.codec((None,)).encode((None,)),
            readonly=serialization.codec((str,)).encode((_READONLY,)),
            read=lambda body: serialization.reader(body).load(Any),
        )


class DubboConnection(asyncio.BufferedProtocol):
    """One connection, of a consumer or a provider, that hands each frame to ``on_frame``.

    It handles the events itself: it answers heartbeat requests, and marks
    itself `readonly` while the provider says it takes no calls. It
    closes once nothing has been read for ``idle_timeout`` seconds. With
    ``heartbeat``, it sends a heartbeat after that many seconds without
    reading or writing. A frame that does not start with the Dubbo magic, or
    whose body is larger than ``max_body`` bytes, closes it.

    Args:
        on_frame: Called with each request and response that is no event,
            in the event loop.
        on_connected: Called once the connection is made, after the TLS
            handshake if any.
        on_closed: Called once a made connection is lost.
        serialization_id: The id each frame it writes carries.
        events: The bodies of the events, in the serialization.
        heartbeat: Seconds of silence before it sends a heartbeat; ``None``
            sends none.
        idle_timeout: Seconds without reading before it closes.
        max_body: Bytes of the largest body it reads or writes.
        pause_reading: Whether it stops reading while it cannot write, so
            that a peer that reads no responses cannot make it buffer more.
    """

    def __init__(
        self,
        *,
        on_frame: _FrameHandler,
        on_connected: Callable[["DubboConnection"], None] | None = None,
        on_closed: Callable[["DubboConnection"], None],
        serialization_id: int,
        events: EventBodies,
        heartbeat: float | None,
        idle_timeout: float,
        max_body: int,
        pause_reading: bool = False,
    ) -> None:
        self.max_body = max_body
        self.peer: str | None = None
        # Set when the provider says it stops serving; a consumer then calls others.
        self.readonly = False
        self._on_frame = on_frame
        self._on_connected = on_connected
        self._on_closed = on_closed
        self._serialization_id = serialization_id
        self._events = events
        self._heartbeat = heartbeat
        self._idle_timeout = idle_timeout
        self._pause_reading = pause_reading
        self._transport: asyncio.Transport | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._last_read = self._last_write = 0.0
        # Received bytes are buffer[start:end]; a partly received frame needs ``frame_size`` bytes from start.
        self._buffer = bytearray(_READ_SIZE)
        self._view = memoryview(self._buffer)
        self._start = self._end = 0
        self._frame_size = 0
        self._closed = anyio.Event()
        self._writable = anyio.Event()
        self._writable.set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def write_frame(self, flags: int, status: int, request_id: int, body: bytes) -> None:
        """Send a frame; ignored once the connection is closing.

        Raises:
            ValueError: The body is larger than ``max_body``.
        """
        if len(body) > self.max_body:
            raise ValueError(f"the body has {len(body)} bytes, more than the {self.max_body} the connection allows")
        if self._transport is None or self._transport.is_closing():
            return

        header = _HEADER.pack(_MAGIC, flags | self._serialization_id, status, request_id, len(body))
        self._transport.write(header + body)
        self._last_write = cast(asyncio.AbstractEventLoop, self._loop).time()

    def announce_shutdown(self) -> None:
        """Tell the consumer that this provider stops taking calls."""
        self.write_frame(FLAG_REQUEST | _FLAG_EVENT, 0, next_request_id(), self._events.readonly)

    async def wait_writable(self) -> None:
        """Wait while the transport buffers more than its high-water mark."""
        if not self._writable.is_set():
            await self._writable.wait()

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()

    def abort(self) -> None:
        """Close at once, dropping the frames not yet sent."""
        if self._transport is not None:
            self._transport.abort()

    async def aclose(self) -> None:
        """Close once the peer has read the frames already written, waiting up to a grace period; abort after it or when cancelled."""
        transport = self._transport
        if transport is None:
            return

        transport.close()
        await close_then_abort(self._closed.wait, lambda: self.closed, transport.abort)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.Transport, transport)
        self._loop = asyncio.get_running_loop()
        self._last_read = self._last_write = self._loop.time()
        peer: Any = transport.get_extra_info("peername")
        if isinstance(peer, tuple):
            self.peer = format_address(*peer[:2])
        self._schedule_tick()
        if self._on_connected is not None:
            self._on_connected(self)

    def get_buffer(self, sizehint: int) -> memoryview:
        if len(self._buffer) - self._end < _READ_SIZE:
            self._make_room()
        return self._view[self._end :]

    def buffer_updated(self, nbytes: int) -> None:
        self._end += nbytes
        self._last_read = cast(asyncio.AbstractEventLoop, self._loop).time()
        buffer, header_size = self._buffer, _HEADER.size
        while self._end - self._start >= header_size:
            magic, flags, status, request_id, length = _HEADER.unpack_from(buffer, self._start)
            if magic != _MAGIC:
                _logger.debug("Received bytes from %s that are not Dubbo; the connection closes", self.peer)
                self.close()
                return
            if length > self.max_body:
                _logger.warning(
                    "Received a body of %d bytes from %s, more than %d; the connection closes",
                    length,
                    self.peer,
                    self.max_body,
                )
                self.close()
                return

            frame_end = self._start + header_size + length
            if frame_end > self._end:
                self._frame_size = header_size + length
                break

            body = bytes(self._view[self._start + header_size : frame_end])
            self._start, self._frame_size = frame_end, 0
            self._receive(flags, status, request_id, body)

        if self._start == self._end:
            if len(self._buffer) > 4 * _READ_SIZE:
                self._buffer = bytearray(_READ_SIZE)
                self._view = memoryview(self._buffer)
            self._start = self._end = 0

    def pause_writing(self) -> None:
        self._writable = anyio.Event()
        if self._pause_reading:
            cast(asyncio.Transport, self._transport).pause_reading()

    def resume_writing(self) -> None:
        self._writable.set()
        if self._pause_reading:
            cast(asyncio.Transport, self._transport).resume_reading()

    def connection_lost(self, exc: Exception | None) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._writable.set()
        self._closed.set()
        self._on_closed(self)

    def _receive(self, flags: int, status: int, request_id: int, body: bytes) -> None:
        if flags & _FLAG_EVENT:
            if flags & FLAG_REQUEST:
                self._receive_event(flags, request_id, body)
            return

        try:
            self._on_frame(self, flags, status, request_id, body)
        except Exception:
            _logger.exception("Cannot handle a frame from %s; the connection closes", self.peer)
            self.close()

    def _receive_event(self, flags: int, request_id: int, body: bytes) -> None:
        try:
            event = self._events.read(body)
        except ValueError:
            _logger.debug("Cannot read an event from %s; it is ignored", self.peer)
            return

        if event is None and flags & FLAG_TWO_WAY:
            self.write_frame(_FLAG_EVENT, _OK, request_id, self._events.heartbeat)
        elif event == _READONLY:
            _logger.info("The provider at %s stops taking calls on this connection", self.peer)
            self.readonly = True
        elif event == _WRITABLE:
            _logger.info("The provider at %s takes calls again on this connection", self.peer)
            self.readonly = False

    def _make_room(self) -> None:
        """Move the received bytes to the front of the buffer, growing it as they come.

        It at most doubles at a time, up to the frame being received, so that
        a peer that only announces a large frame takes no memory for it.
        """
        unread = self._end - self._start
        size = len(self._buffer)
        if unread + _READ_SIZE > size:
            size = max(unread + _READ_SIZE, min(2 * size, self._frame_size + _READ_SIZE))
        if size > len(self._buffer):
            buffer = bytearray(size)
            buffer[:unread] = self._view[self._start : self._end]
            self._view.release()
            self._buffer, self._view = buffer, memoryview(buffer)
        elif self._start:
            self._buffer[:unread] = self._buffer[self._start : self._end]
        self._start, self._end = 0, unread

    def _schedule_tick(self) -> None:
        interval = self._idle_timeout if self._heartbeat is None else min(self._heartbeat, self._idle_timeout)
        self._timer = cast(asyncio.AbstractEventLoop, self._loop).call_later(interval, self._tick)

    def _tick(self) -> None:
        now = cast(asyncio.AbstractEventLoop, self._loop).time()
        if now - self._last_read >= self._idle_timeout:
            _logger.info("Read nothing from %s for %s seconds; the connection closes", self.peer, self._idle_timeout)
            self.close()
            return

        heartbeat = self._heartbeat
        if heartbeat is not None and (now - self._last_read >= heartbeat or now - self._last_write >= heartbeat):
            self.write_frame(FLAG_REQUEST | FLAG_TWO_WAY | _FLAG_EVENT, 0, next_request_id(), self._events.heartbeat)
        self._schedule_tick()
