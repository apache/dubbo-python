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

import typing
from collections.abc import Awaitable, Callable
from enum import IntEnum
from types import TracebackType
from typing import Self, TypeAlias

from dubbo.extension import Resource, extension_point
from dubbo.url import URL

__all__ = [
    "H2Client",
    "H2ErrorCode",
    "H2Header",
    "H2Headers",
    "H2Server",
    "H2Stream",
    "H2StreamHandler",
]

# A lowercase HTTP/2 field name and its raw value.
H2Header: TypeAlias = tuple[bytes, bytes]
# An ordered field section; repeated field names remain separate entries.
H2Headers: TypeAlias = tuple[H2Header, ...]


class H2ErrorCode(IntEnum):
    """The HTTP/2 error codes of RFC 9113 section 7, carried by RST_STREAM and GOAWAY.

    Attributes:
        NO_ERROR: Not the result of an error, such as a GOAWAY for a graceful shutdown.
        PROTOCOL_ERROR: An unspecific protocol error.
        INTERNAL_ERROR: An unexpected internal error.
        FLOW_CONTROL_ERROR: The peer violated flow control.
        SETTINGS_TIMEOUT: A SETTINGS frame was not acknowledged in time.
        STREAM_CLOSED: A frame arrived after the stream was half-closed.
        FRAME_SIZE_ERROR: A frame had an invalid size.
        REFUSED_STREAM: The stream was refused before any application processing.
        CANCEL: The stream is no longer needed.
        COMPRESSION_ERROR: The field compression context cannot be maintained.
        CONNECT_ERROR: The connection of a CONNECT request was reset or closed abnormally.
        ENHANCE_YOUR_CALM: The peer behaves in a way that might generate excessive load.
        INADEQUATE_SECURITY: The transport does not meet minimum security requirements.
        HTTP_1_1_REQUIRED: The endpoint requires HTTP/1.1 instead of HTTP/2.
    """

    NO_ERROR = 0x00
    PROTOCOL_ERROR = 0x01
    INTERNAL_ERROR = 0x02
    FLOW_CONTROL_ERROR = 0x03
    SETTINGS_TIMEOUT = 0x04
    STREAM_CLOSED = 0x05
    FRAME_SIZE_ERROR = 0x06
    REFUSED_STREAM = 0x07
    CANCEL = 0x08
    COMPRESSION_ERROR = 0x09
    CONNECT_ERROR = 0x0A
    ENHANCE_YOUR_CALM = 0x0B
    INADEQUATE_SECURITY = 0x0C
    HTTP_1_1_REQUIRED = 0x0D


class H2Stream(typing.Protocol):
    """One bidirectional HTTP/2 stream.

    Callers use each direction in order: initial fields, zero or more data
    operations, then trailers or an end operation.

    One send and one receive operation may be active concurrently. Starting a
    second operation in the same direction before the first completes raises
    `H2StreamError`; operations are never silently queued. Outbound operations
    return after the connection accepts their complete input subject to flow
    control and transport backpressure; they do not wait for peer processing.

    Implementations translate network-backend and HTTP/2-engine failures into
    Dubbo's transport exception hierarchy. A remote reset raises
    `H2StreamResetError`, while loss of the owning connection raises
    `H2ConnectionError`. Once the peer ends its direction normally, receives
    return what is left, then `b""`. Task cancellation propagates unchanged.
    Cancelling an outbound operation after protocol submission resets the
    stream before propagating cancellation. Cancelling a receive leaves the
    stream usable; an exact receive puts the bytes it collected back at the
    front, without returning their window credit again. Closing
    the context resets a stream whose directions have not both ended, with
    `H2ErrorCode.CANCEL`; a server that has ended its response instead resets
    with `H2ErrorCode.NO_ERROR` once the response is written, which asks the
    client to stop its request. A client keeps a whole response it received
    before such a NO_ERROR reset readable; only its sends raise
    `H2StreamResetError`. Data that arrives after the context closes is
    discarded, and its flow-control credit released.
    """

    @property
    def stream_id(self) -> int:
        """The HTTP/2 stream identifier, unique on its connection."""
        ...

    @property
    def peer(self) -> str | None:
        """The address of the other endpoint, as ``host:port`` with an IPv6 host in brackets.

        ``None`` when the transport does not report one.
        """
        ...

    async def send_headers(self, headers: H2Headers, *, end_stream: bool = False) -> None:
        """Send ``headers``, the ordered initial field section; ``end_stream`` also ends the local direction.

        Client streams returned by `H2Client.open_stream` have already sent
        this section.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another send is active, initial fields were already
                sent, or the field section is invalid for this stream.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def send_data(self, data: bytes, *, end_stream: bool = False) -> None:
        """Send ``data``, waiting for flow-control and transport capacity; ``end_stream`` also ends the local direction.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another send is active, the local direction has
                ended, or the operation is invalid for this stream.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def send_trailers(self, trailers: H2Headers) -> None:
        """Send ``trailers``, the ordered trailing field section, and end the local direction.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another send is active, the local direction has
                ended, or the field section is invalid for this stream.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def end(self) -> None:
        """End the local direction without trailers.

        The operation is idempotent after the local direction has ended.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another send is active or the operation is invalid
                for this stream.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def receive_headers(self) -> H2Headers:
        """Return the peer's ordered initial field section, which comes before its data.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another receive is active or the peer ended the
                stream without initial fields.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def receive_data(self, max_bytes: int = 64 * 1024) -> bytes:
        """Return one nonempty chunk of at most ``max_bytes`` application bytes, or ``b""`` once the peer has ended its direction.

        The bytes returned count as consumed for HTTP/2 flow control.

        Raises:
            ValueError: ``max_bytes`` is not positive.
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another receive is active or the receive state is
                invalid.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def receive_data_exactly(self, nbytes: int) -> bytes:
        """Return ``nbytes`` application bytes, or fewer, ``b""`` for none, once the peer has ended its direction.

        Bytes collected toward the result count as consumed for flow control
        as they are taken. Cancellation puts the bytes collected so far back,
        so the next receive starts with them.

        Raises:
            ValueError: ``nbytes`` is negative.
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another receive is active or the receive state is
                invalid.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def receive_trailers(self) -> H2Headers | None:
        """Return the peer's ordered trailing field section after its data, or ``None`` when it ended its direction without one.

        Raises:
            H2StreamResetError: The peer reset the stream.
            H2StreamError: Another receive is active or the receive state is
                invalid.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def reset(self, error_code: int = H2ErrorCode.CANCEL) -> None:
        """Abort the stream with ``error_code``, a registered or extension HTTP/2 error code.

        Raises:
            ValueError: ``error_code`` is outside the HTTP/2 wire range.
            H2StreamError: The stream cannot be reset in its current state.
            H2ConnectionError: The owning connection failed or closed.
        """
        ...

    async def __aenter__(self) -> Self:
        """Enter this stream's managed lifetime."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the stream without suppressing an active exception.

        An unfinished stream is reset and unread flow-control credit is
        released. A cleanup failure is suppressed only when preserving an
        exception already leaving the context.

        Raises:
            H2Error: Cleanup fails and no exception is already active.
        """
        ...


# An application coroutine invoked once for each peer-initiated stream.
H2StreamHandler: TypeAlias = Callable[[H2Stream], Awaitable[None]]


@extension_point("apache_dubbo.transport.h2.client", default="aio")
class H2Client(Resource, typing.Protocol):
    """Reusable client-side HTTP/2 connections to one endpoint.

    The implementation is named by the ``client`` parameter, ``aio`` when
    absent, and created with a URL whose host and port name the server. The
    TLS parameters configure it as `dubbo.transport.tls.get_ssl_context` reads
    them, and these HTTP/2 parameters each connection, for the side that sets
    them:

    - ``max-concurrent-streams``: streams the peer may open at once; 100
      when absent. This side opens at most as many as the peer allows.
    - ``initial-window-size``: bytes the peer may send on one stream before
      it waits for more credit. When absent, the window starts at 1 MiB and
      grows with the bandwidth-delay product measured on the connection, up
      to 16 MiB.
    - ``connection-initial-window-size``: bytes the peer may send on the
      connection before it waits for more credit; 16 MiB when absent.
    - ``max-header-list-size``: bytes of the largest field section accepted;
      64 KiB when absent.
    - ``keep-alive-interval``: whole milliseconds without inbound traffic
      before a PING checks the connection; no PING when absent.
    - ``keep-alive-timeout``: whole milliseconds to wait for the PING
      acknowledgement before the connection fails; 20000 when absent.

    And this one, for the client alone:

    - ``connect-timeout``: whole milliseconds to establish a connection,
      the TLS handshake included; 3000 when absent.

    The client may be shared by concurrent callers. It assigns each opened
    stream to a usable connection and keeps physical connection state private.
    Entering it starts connecting in the background, so that `available`
    tells whether the server can be reached before the first call.
    Task cancellation propagates unchanged. It holds no task group or cancel
    scope of the tasks that use it, so that its owner may close it from any
    task.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    @property
    def available(self) -> bool:
        """Whether a connection to the server is established now.

        It is false until an attempt to connect succeeds, and from a failed
        attempt or a lost connection until the next succeeds, while the
        client waits a backoff, longer after each failure in a row, and then
        tries again. Opening a stream still tries to connect while it is
        false. A client that does not say otherwise is always available.
        """
        return True

    async def open_stream(self, headers: H2Headers, *, end_stream: bool = False) -> H2Stream:
        """Open a stream, send ``headers``, its ordered initial field section, and return the stream.

        It waits for room for one more stream; ``end_stream`` also ends the
        local direction. The stream returns once its headers have entered
        the connection's bounded write path. A cancellation after the stream
        is allocated resets it before propagating.

        Raises:
            RuntimeError: The client is closed.
            H2StreamResetError: The peer reset the newly allocated stream
                before it could be returned.
            H2StreamError: The initial field section is invalid for a new
                stream.
            H2ConnectionError: A connection cannot be established or fails
                while opening the stream.
        """
        ...

    async def aclose(self) -> None:
        """Stop opening streams and close all owned connections.

        Each connection sends a final GOAWAY and closes once its open streams
        finish, or is aborted after a grace period. A cancelled close aborts
        the connections at once. Closing again waits for the close under
        way; it returns once each connection has reported transport closure.
        """
        ...


@extension_point("apache_dubbo.transport.h2.server", default="aio")
class H2Server(Resource, typing.Protocol):
    """Serves HTTP/2 streams with the handler given when the server is created.

    The implementation is named by the ``server`` parameter, ``aio`` when
    absent, and created with a URL whose host is the interface to bind, such
    as ``0.0.0.0`` for every IPv4 interface, and whose port is 0 for an
    ephemeral port. The HTTP/2 parameters of `H2Client` configure each
    connection, the TLS parameters configure it as
    `dubbo.transport.tls.get_ssl_context` reads them, and ``shutwait`` is the
    whole milliseconds closing waits for running handlers, 10000 when absent.

    Entering the server starts listening; closing it stops. The server is
    single-use and owns its listener, connections and handler tasks. Each
    accepted stream runs its own handler; an ordinary handler failure resets
    only that stream. When the peer resets the stream or the connection
    fails, the handler is cancelled as AnyIO cancels, so that what it
    shields from cancellation finishes first.

    Attributes:
        url: The URL the instance was created with.
        handler: The handler each accepted stream runs.
    """

    url: URL
    handler: H2StreamHandler

    def __init__(self, url: URL, handler: H2StreamHandler) -> None:
        self.url = url
        self.handler = handler

    @property
    def address(self) -> tuple[str, int]:
        """The host and port actually bound, with port 0 resolved.

        Raises:
            RuntimeError: The server is not listening.
        """
        ...

    def announce_shutdown(self) -> None:
        """Send the connections established now a GOAWAY that refuses no stream, and keep serving.

        Peers open their next streams on new connections, which the server
        still accepts and serves; `aclose` stops serving.
        """
        ...

    async def aclose(self) -> None:
        """Stop accepting work, let running handlers finish, then release everything.

        New connections are refused at once, and established ones receive a
        GOAWAY so peers open no more streams. Handlers still running when the
        grace period ends are cancelled. Connections then close once the
        responses they still queue are written, or are aborted after a
        second. A cancelled close cancels the handlers and aborts the
        connections at once. Closing again waits for the close under way.
        """
        ...

    async def __aenter__(self) -> Self:
        """Start listening.

        Raises:
            RuntimeError: The server has already been started.
            OSError: The address cannot be bound.
            ValueError: A host name with port 0 would listen on several
                ports, one per address.
        """
        ...
