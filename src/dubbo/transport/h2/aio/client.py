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
import ipaddress
from typing import Any, Self

import anyio
import ngh2

from dubbo.constants import CONNECT_TIMEOUT_KEY, DEFAULT_CONNECT_TIMEOUT
from dubbo.transport.h2.base import H2Client, H2Headers
from dubbo.transport.h2.exceptions import H2ConnectionError
from dubbo.transport.tls import get_ssl_context, server_hostname
from dubbo.url import URL
from dubbo.utils import Dialer, release_shield
from dubbo.utils.converters import milliseconds

from .connection import AioH2Connection
from .stream import AioH2Stream

__all__ = ["AioH2Client"]

_HAPPY_EYEBALLS_DELAY = 0.25


class AioH2Client(H2Client):
    """Connects to one HTTP/2 endpoint through asyncio.

    Without TLS, the client uses prior-knowledge HTTP/2 over cleartext TCP.
    With TLS, it verifies that the handshake selected ``h2`` through ALPN and
    never falls back to HTTP/1.1. Concurrent tasks may share the client, but
    after the first connection attempt all asynchronous calls and returned
    streams must remain on that asyncio event loop. The client owns one active
    connection plus any predecessor draining after GOAWAY.

    Entering the client starts connecting in the background. One attempt
    runs at a time and lasts at most the connect timeout; callers that open
    streams meanwhile wait for it, and one that stops waiting leaves it
    running. After an attempt fails or the connection is lost, the client
    connects again in the background after a backoff.

    ``url`` names the server host and port, with the parameters `H2Client`
    describes, plus ``stream-send-buffer-size``: bytes of a stream's body
    queued for flow control or the socket before a send waits, 256 KiB when
    absent.

    Raises:
        ValueError: The URL has no host or port, a parameter is invalid, or
            the connect timeout is not positive.
        OSError: A TLS file cannot be loaded.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)

        if url.host is None or url.port is None:
            raise ValueError(f"an HTTP/2 client needs a host and a port: {url}")

        connect_timeout = url.get_parameter(CONNECT_TIMEOUT_KEY, milliseconds, DEFAULT_CONNECT_TIMEOUT)
        if not connect_timeout > 0:
            raise ValueError(f"URL parameter {CONNECT_TIMEOUT_KEY!r} must be positive")

        self._host = url.host
        self._port = url.port
        self._ssl_context = get_ssl_context(url, server=False, alpn=("h2",))
        self._server_hostname = server_hostname(url) if self._ssl_context is not None else None
        self._connect_timeout = connect_timeout
        self._host_is_name = _is_name(url.host)

        self._active_connection: AioH2Connection | None = None
        self._draining_connections: set[AioH2Connection] = set()
        self._dialer = Dialer(self._open_connection)
        self._closed = False
        self._shutdown: asyncio.Task[None] | None = None

    @property
    def available(self) -> bool:
        return not self._closed and self._dialer.connected

    async def open_stream(self, headers: H2Headers, *, end_stream: bool = False) -> AioH2Stream:
        replaced = False
        while True:
            connection = await self._get_or_open_connection()
            stream = await connection.open_stream(headers, end_stream=end_stream)
            if stream is not None:
                return stream
            if replaced:
                connection.raise_if_failed()
                raise H2ConnectionError("the HTTP/2 connection became unavailable before opening a stream")
            replaced = True

    async def aclose(self) -> None:
        """Close the client and its connections for good.

        The connections close together, each once its open streams have
        finished and the server has read what was sent, or after a second. A
        connection attempt under way is abandoned. A cancelled close aborts
        the connections at once. Closing again waits for the close under way.
        """
        if self._shutdown is None:
            self._closed = True
            self._shutdown = asyncio.get_running_loop().create_task(self._shut_down())

        shutdown = self._shutdown
        try:
            await asyncio.wait((shutdown,))
        except BaseException:
            # A cancelled close aborts at once and waits only for that.
            shutdown.cancel()
            self._dialer.close()
            connections = self._owned()
            for connection in connections:
                connection.abort()
            with release_shield():
                await asyncio.wait((shutdown,))
                for connection in connections:
                    await connection.wait_closed()
            raise

        # A shutdown cancelled by an earlier close has finished at once.
        if not shutdown.cancelled():
            shutdown.result()

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("the HTTP/2 client is closed")
        self._dialer.start()
        return self

    async def _get_or_open_connection(self) -> AioH2Connection:
        """Reuse an accepting connection, or wait for the attempt that establishes its replacement."""
        if self._closed:
            raise RuntimeError("the HTTP/2 client is closed")
        current = self._active_connection
        if current is not None and current.accepting_streams:
            return current

        connection = await self._dialer.connect()
        if connection is None:
            raise RuntimeError("the HTTP/2 client is closed")
        return connection

    async def _open_connection(self) -> AioH2Connection:
        """Establish and publish one replacement connection within the connect timeout."""
        current = self._active_connection
        if current is not None and not current.closed:
            self._draining_connections.add(current)

        connection = AioH2Connection(
            ngh2.Role.CLIENT,
            self.url,
            require_h2_alpn=self._ssl_context is not None,
            on_closed=self._connection_closed,
        )
        # Publish before awaiting so a concurrent close owns this connection.
        self._active_connection = connection
        protocol_created = False

        def create_protocol() -> AioH2Connection:
            """Record that asyncio now owns the protocol lifecycle."""
            nonlocal protocol_created
            protocol_created = True
            return connection

        loop = asyncio.get_running_loop()
        # Only the standard library loops race addresses; uvloop rejects the argument. An IP address has none to
        # race, and a cancelled race leaks its socket in CPython 3.11 to 3.15.
        race = self._host_is_name and isinstance(loop, asyncio.BaseEventLoop)
        options: dict[str, Any] = {"happy_eyeballs_delay": _HAPPY_EYEBALLS_DELAY} if race else {}
        try:
            # TimeoutError is an OSError. A server counts as answering once its SETTINGS arrive, not when TCP
            # accepts, which a proxy in front of a gone server still does.
            with anyio.fail_after(self._connect_timeout):
                await loop.create_connection(
                    create_protocol,
                    self._host,
                    self._port,
                    ssl=self._ssl_context,
                    server_hostname=self._server_hostname,
                    **options,
                )
                await connection.wait_established()
        except BaseException as error:
            # The connection carried no stream, so it is released at once, even when cancelled. Once asyncio has the
            # protocol, it reports the transport closed, which may still be on its way.
            if protocol_created:
                connection.start_close()
                connection.abort()
            else:
                connection.abandon()
            with release_shield():
                await connection.wait_closed()
            if isinstance(error, OSError):
                raise H2ConnectionError(f"failed to connect to {self._host}:{self._port}") from error
            raise

        return connection

    async def _shut_down(self) -> None:
        for connection in self._owned():
            connection.start_close()
        # An attempt under way is abandoned; a connection it completed meanwhile is among those closed below.
        await self._dialer.aclose()

        async with anyio.create_task_group() as closing:
            for connection in self._owned():
                closing.start_soon(connection.aclose)

    def _owned(self) -> tuple[AioH2Connection, ...]:
        """Return the connections still open: the active one and those draining."""
        active = () if self._active_connection is None else (self._active_connection,)
        return (*self._draining_connections, *active)

    def _connection_closed(self, connection: AioH2Connection) -> None:
        """Forget a connection after asyncio reports its transport closed, and connect again if it was the active one."""
        self._draining_connections.discard(connection)
        if self._active_connection is connection:
            self._active_connection = None
            # Ignored while the attempt that opened it is still under way, which reports the failure itself.
            self._dialer.lost()


def _is_name(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False
