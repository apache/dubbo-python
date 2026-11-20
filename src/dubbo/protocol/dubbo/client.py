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
from typing import Self

import anyio

from dubbo.exceptions import RpcError, Status
from dubbo.extension import Resource
from dubbo.serialization import JavaSerialization
from dubbo.transport.tls import get_ssl_context, server_hostname
from dubbo.url import URL
from dubbo.utils import Dialer

from .connection import (
    FLAG_REQUEST,
    FLAG_TWO_WAY,
    SERIALIZATION_MASK,
    ConnectionSettings,
    DubboConnection,
    EventBodies,
    next_request_id,
)

__all__ = ["DubboClient"]


class DubboClient(Resource):
    """The connection to one provider address, which opens in the background once entered and again after it is lost.

    One attempt to connect runs at a time and lasts at most the
    `ConnectionSettings.connect_timeout`; calls made meanwhile wait for it,
    and one that stops waiting leaves it running. After an attempt fails or
    the connection is lost, the client connects again in the background
    after a backoff. A call waits for its response until the connection
    closes; the caller bounds it. A response in another serialization than
    the request fails the call.

    The client is available while a connection is established on which
    the provider takes calls: not until an attempt succeeds, nor from a
    failed attempt or a lost connection until the next succeeds, nor once
    closed. A call still connects while it is unavailable.
    """

    def __init__(self, url: URL, serialization: JavaSerialization, serialization_id: int) -> None:
        if url.host is None or url.port is None:
            raise ValueError(f"a Dubbo client needs a host and a port: {url}")

        self.address = (url.host, url.port)
        self._settings = ConnectionSettings.from_url(url)
        self._ssl_context = get_ssl_context(url, server=False)
        self._server_hostname = server_hostname(url) if self._ssl_context is not None else None
        self._serialization_id = serialization_id
        self._events = EventBodies.from_serialization(serialization)
        self._connection: DubboConnection | None = None
        self._dialer = Dialer(self._open_connection)
        self._pending: dict[int, asyncio.Future[tuple[int, bytes]]] = {}
        self._closed = False

    @property
    def available(self) -> bool:
        connection = self._connection
        return not self._closed and self._dialer.connected and connection is not None and not connection.readonly

    async def call(self, body: bytes) -> tuple[int, bytes]:
        """Send a two-way request with ``body`` and return the status and the body of its response.

        Raises:
            RpcError: The provider cannot be reached, the connection is lost
                before the response, or ``body`` is too large.
        """
        connection = await self._connect()
        request_id = next_request_id()
        # An asyncio future, which the connection, an asyncio protocol, resolves from its callback.
        future: asyncio.Future[tuple[int, bytes]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await connection.wait_writable()
            try:
                connection.write_frame(FLAG_REQUEST | FLAG_TWO_WAY, 0, request_id, body)
            except ValueError as error:
                raise RpcError(Status.RESOURCE_EXHAUSTED, str(error)) from None
            return await future
        finally:
            del self._pending[request_id]

    async def aclose(self) -> None:
        self._closed = True
        await self._dialer.aclose()
        connection = self._connection
        if connection is not None:
            await connection.aclose()

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("the Dubbo client is closed")
        self._dialer.start()
        return self

    async def _connect(self) -> DubboConnection:
        """Return the open connection, or wait for the attempt that opens one."""
        if self._closed:
            raise RpcError(Status.UNAVAILABLE, "the Dubbo client is closed")
        connection = self._connection
        if connection is not None and not connection.closed:
            return connection

        connection = await self._dialer.connect()
        if connection is None:
            raise RpcError(Status.UNAVAILABLE, "the Dubbo client is closed")
        return connection

    async def _open_connection(self) -> DubboConnection:
        host, port = self.address
        try:
            with anyio.fail_after(self._settings.connect_timeout):
                _, connection = await asyncio.get_running_loop().create_connection(
                    self._create_connection,
                    host,
                    port,
                    ssl=self._ssl_context,
                    server_hostname=self._server_hostname,
                )
        except (OSError, TimeoutError) as error:
            raise RpcError(Status.UNAVAILABLE, f"cannot connect to {host}:{port}: {error}") from None

        self._connection = connection
        return connection

    def _create_connection(self) -> DubboConnection:
        return DubboConnection(
            on_frame=self._receive,
            on_closed=self._lost,
            serialization_id=self._serialization_id,
            events=self._events,
            heartbeat=self._settings.heartbeat,
            idle_timeout=self._settings.idle_timeout,
            max_body=self._settings.max_body,
        )

    def _receive(self, connection: DubboConnection, flags: int, status: int, request_id: int, body: bytes) -> None:
        if flags & FLAG_REQUEST:
            return

        future = self._pending.get(request_id)
        if future is None or future.done():
            return

        received = flags & SERIALIZATION_MASK
        if received != self._serialization_id:
            message = f"the response is in serialization {received}, not {self._serialization_id} as the request"
            future.set_exception(RpcError(Status.INTERNAL, message))
        else:
            future.set_result((status, body))

    def _lost(self, connection: DubboConnection) -> None:
        if connection is not self._connection:
            return

        # Each caller raises its own error, so that no traceback gathers the frames of the others.
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RpcError(Status.UNAVAILABLE, f"the connection to {connection.peer} closed"))
        self._dialer.lost()
