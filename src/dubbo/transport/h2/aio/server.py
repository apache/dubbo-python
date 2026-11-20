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
import logging
from contextlib import suppress
from types import TracebackType
from typing import Self

import anyio
import ngh2

from dubbo.constants import DEFAULT_SHUTWAIT, SHUTWAIT_KEY
from dubbo.transport.h2.base import H2ErrorCode, H2Server, H2StreamHandler
from dubbo.transport.h2.exceptions import H2Error
from dubbo.transport.listener import abort_handshakes, create_listener
from dubbo.transport.tls import get_ssl_context, ssl_handshake_timeout
from dubbo.url import URL
from dubbo.utils import release_shield, wait_then_cancel
from dubbo.utils.converters import milliseconds

from .connection import AioH2Connection
from .stream import AioH2Stream
from .tasks import join_shielded

__all__ = ["AioH2Server"]

_logger = logging.getLogger(__name__)


class AioH2Server(H2Server):
    """Serves HTTP/2 through asyncio.

    Without TLS, the server accepts prior-knowledge HTTP/2 over cleartext
    TCP. With TLS, it requires the handshake to select ``h2`` through ALPN and
    never accepts HTTP/1.1. Entering the server starts listening; it is
    single-use and owns its listener, connections, stream contexts and
    handler tasks, all of which must stay on the event loop it was entered on.

    ``url`` names the interface and port to bind, with the parameters
    `H2Server` describes, plus ``ssl-handshake-timeout``: the whole
    milliseconds a TLS handshake may take, 10000 when absent, and
    ``stream-send-buffer-size`` as `AioH2Client` describes it. When the host
    is a name that resolves to multiple addresses, use a fixed port so every
    listener shares one discoverable endpoint. Each accepted stream runs the
    coroutine function ``handler`` in its own task. An ordinary handler
    failure is logged and resets only its stream.

    Raises:
        ValueError: The URL has no host or port, a parameter is invalid, or
            the TLS handshake timeout is not positive.
        OSError: A TLS file cannot be loaded.
    """

    def __init__(self, url: URL, handler: H2StreamHandler) -> None:
        super().__init__(url, handler)

        if url.host is None or url.port is None:
            raise ValueError(f"an HTTP/2 server needs a host and a port: {url}")

        self._host = url.host
        self._port = url.port
        self._ssl_context = get_ssl_context(url, server=True, alpn=("h2",))
        self._ssl_handshake_timeout = ssl_handshake_timeout(url)
        self._shutwait = url.get_parameter(SHUTWAIT_KEY, milliseconds, DEFAULT_SHUTWAIT)

        self._listener: asyncio.Server | None = None
        self._address: tuple[str, int] | None = None
        self._connections: set[AioH2Connection] = set()
        self._handlers: set[asyncio.Task[None]] = set()
        self._started = False
        self._closing = False
        self._shutdown: asyncio.Task[None] | None = None
        # A connection checks the HTTP/2 settings as it is made, so a server with invalid ones fails here, not on each accept.
        self._create_connection()

    @property
    def address(self) -> tuple[str, int]:
        if self._address is None or self._closing:
            raise RuntimeError("the HTTP/2 server is not listening")
        return self._address

    def announce_shutdown(self) -> None:
        for connection in tuple(self._connections):
            connection.announce_shutdown()

    async def aclose(self) -> None:
        if self._shutdown is None:
            self._closing = True
            self._shutdown = asyncio.get_running_loop().create_task(self._shut_down())

        shutdown = self._shutdown
        try:
            await asyncio.wait((shutdown,))
        except BaseException:
            # A cancelled close shuts down at once and waits only for that.
            shutdown.cancel()
            with suppress(asyncio.CancelledError):
                await join_shielded(shutdown)
            raise

        # A shutdown cancelled by an earlier close has finished at once.
        if not shutdown.cancelled():
            shutdown.result()

    async def __aenter__(self) -> Self:
        """Start listening.

        Raises:
            RuntimeError: The server has already been started or closed.
            OSError: The address cannot be bound.
            ValueError: A host name with port 0 would listen on several
                ports, one per address.
        """
        if self._started or self._closing:
            raise RuntimeError("the HTTP/2 server can only be started once")
        self._started = True

        # Accepting waits until the server owns the listener.
        listener, address = await create_listener(
            self._create_connection, self._host, self._port, self._ssl_context, self._ssl_handshake_timeout
        )
        if self._closing:
            listener.close()
            await listener.wait_closed()
            raise RuntimeError("the HTTP/2 server closed while it started")

        self._listener, self._address = listener, address
        try:
            await listener.start_serving()
        except BaseException:
            # No one owns the server until it has started, so a start that fails closes its listener.
            self._closing = True
            listener.close()
            raise

        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        # Leaving under a cancellation stops at once, whether or not the cancellation is still delivered.
        if exc_type is not None and issubclass(exc_type, anyio.get_cancelled_exc_class()):
            with anyio.CancelScope() as scope:
                scope.cancel()
                await self.aclose()
            return
        await self.aclose()

    def _create_connection(self) -> AioH2Connection:
        return AioH2Connection(
            ngh2.Role.SERVER,
            self.url,
            require_h2_alpn=self._ssl_context is not None,
            on_connected=self._connection_connected,
            on_stream=self._start_handler,
            on_closed=self._connections.discard,
        )

    def _connection_connected(self, connection: AioH2Connection) -> None:
        """Own an established connection, or abort one that arrives while the server shuts down, as it carries nothing."""
        if self._closing:
            connection.start_close()
            connection.abort()
        else:
            self._connections.add(connection)

    def _start_handler(self, stream: AioH2Stream) -> None:
        if self._closing:
            with suppress(H2Error):
                stream._reset(H2ErrorCode.REFUSED_STREAM)
            return

        task = asyncio.get_running_loop().create_task(self._run_handler(stream))
        self._handlers.add(task)
        task.add_done_callback(self._handlers.discard)

    async def _run_handler(self, stream: AioH2Stream) -> None:
        """Run the handler for one stream, resetting the stream if the handler leaves it unfinished."""
        try:
            async with stream:
                # The handler is cancelled alone when its stream is aborted, in a scope so that its shields hold.
                # The scope is made in the task: outside one, AnyIO may not tell which event loop runs.
                with anyio.CancelScope() as scope:
                    stream._on_abort = scope.cancel
                    await self.handler(stream)
        except H2Error:
            pass
        except Exception:
            _logger.exception("The HTTP/2 stream handler failed")

    async def _shut_down(self) -> None:
        listener = self._listener
        try:
            async with anyio.create_task_group() as task_group:
                if listener is not None:
                    listener_waiting = anyio.Event()
                    loop = asyncio.get_running_loop()

                    async def wait_for_listener() -> None:
                        # Started before close: older asyncio versions stop tracking clients once the listener closes.
                        # The callback runs only after wait_closed() reaches its first suspension.
                        loop.call_soon(listener_waiting.set)
                        await listener.wait_closed()

                    task_group.start_soon(wait_for_listener)
                    await listener_waiting.wait()
                    listener.close()

                for connection in tuple(self._connections):
                    connection.announce_shutdown()

                await wait_then_cancel(self._handlers, self._shutwait)

                # Each closes once its queued responses are written, or aborts after a grace period.
                async with anyio.create_task_group() as closing:
                    for connection in tuple(self._connections):
                        closing.start_soon(connection.aclose)

                if listener is not None:
                    abort_handshakes(listener)
        except BaseException:
            # Cancelled: the listener and the connections still open close at once.
            if listener is not None:
                listener.close()
                abort_handshakes(listener)
            for connection in tuple(self._connections):
                connection.abort()
            with release_shield():
                if self._handlers:
                    await asyncio.wait(tuple(self._handlers))
                for connection in tuple(self._connections):
                    await connection.wait_closed()
            raise
