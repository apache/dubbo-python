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
from typing import Any

import anyio
import pytest

import dubbo.utils.dialer as dialer_module
from dubbo.exceptions import RpcError, Status
from dubbo.protocol.dubbo.client import DubboClient
from dubbo.protocol.dubbo.connection import DubboConnection
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL

pytestmark = pytest.mark.anyio


class _Transport(asyncio.Transport):
    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return default

    def is_closing(self) -> bool:
        return False

    def write(self, data: Any) -> None:
        pass

    def close(self) -> None:
        pass


def _client(**parameters: str) -> DubboClient:
    url = URL(protocol="dubbo", host="127.0.0.1", port=1, parameters=parameters)
    return DubboClient(url, Hessian2Serialization(url), 2)


def _connected(protocol_factory: Any) -> tuple[_Transport, DubboConnection]:
    transport = _Transport()
    connection = protocol_factory()
    connection.connection_made(transport)
    return transport, connection


async def test_call_that_stops_waiting_leaves_the_attempt_to_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    started = anyio.Event()
    release = anyio.Event()
    attempts = 0

    async def slow_create_connection(protocol_factory, host, port, **kwargs):
        nonlocal attempts
        attempts += 1
        started.set()
        await release.wait()
        return _connected(protocol_factory)

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", slow_create_connection)
    client = _client()

    with anyio.move_on_after(0.01):
        await client._connect()
    await started.wait()
    # The attempt runs on.
    assert client._dialer._attempt is not None

    release.set()
    connection = await client._connect()

    assert attempts == 1
    assert client.available
    connection.connection_lost(None)
    await client.aclose()


async def test_an_unanswered_attempt_fails_at_the_connect_timeout_and_leaves_the_client_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def unanswered_create_connection(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        await anyio.sleep_forever()

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", unanswered_create_connection)
    # No retry within the test, so that the state after the failure stays.
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([60.0] * 3))
    async with _client(**{"connect-timeout": "50"}) as client:
        # Only the connect timeout ends the attempt; the bound only keeps a broken timeout from hanging.
        with anyio.fail_after(5):
            while client._dialer._attempt is not None:
                await anyio.sleep(0.01)

        assert (attempts, client.available) == (1, False)


async def test_failed_attempt_fails_each_waiting_call_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refused_create_connection(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", refused_create_connection)
    client = _client()

    with pytest.raises(RpcError, match="cannot connect") as caught:
        await client._connect()

    assert caught.value.status is Status.UNAVAILABLE
    assert not client.available
    await client.aclose()


async def test_entered_client_connects_and_reconnects_in_the_background(monkeypatch: pytest.MonkeyPatch) -> None:
    connected = anyio.Event()
    connections: list[DubboConnection] = []

    async def create_connection(protocol_factory, host, port, **kwargs):
        transport, connection = _connected(protocol_factory)
        connections.append(connection)
        connected.set()
        return transport, connection

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", create_connection)
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.01] * 3))
    async with _client() as client:
        with anyio.fail_after(5):
            await connected.wait()
        await anyio.wait_all_tasks_blocked()
        assert client.available

        connected = anyio.Event()
        connections[0].connection_lost(None)
        assert not client.available
        with anyio.fail_after(5):
            await connected.wait()
        await anyio.wait_all_tasks_blocked()

        assert len(connections) == 2
        assert client.available
        connections[1].connection_lost(None)


async def test_each_call_pending_on_a_lost_connection_raises_its_own_error(monkeypatch: pytest.MonkeyPatch) -> None:
    connections: list[DubboConnection] = []

    async def create_connection(protocol_factory, host, port, **kwargs):
        transport, connection = _connected(protocol_factory)
        connections.append(connection)
        return transport, connection

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", create_connection)
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([60.0] * 3))
    raised: list[RpcError] = []

    async def call(client: DubboClient) -> None:
        try:
            await client.call(b"body")
        except RpcError as error:
            raised.append(error)

    async with _client() as client, anyio.create_task_group() as calls:
        calls.start_soon(call, client)
        calls.start_soon(call, client)
        await anyio.wait_all_tasks_blocked()
        connections[0].connection_lost(None)

    first, second = raised
    assert first is not second
    assert first.status is second.status is Status.UNAVAILABLE
