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
from typing import cast

import anyio
import pytest

from dubbo.transport.h2.aio import AioH2Server
from dubbo.transport.h2.aio.connection import AioH2Connection

pytestmark = pytest.mark.anyio


class _RecordingSocket:
    def __init__(self, host: str = "127.0.0.1", port: int = 20_880) -> None:
        self._address = host, port

    def getsockname(self) -> tuple[str, int]:
        return self._address


class _RecordingServer:
    def __init__(self) -> None:
        self.sockets = [_RecordingSocket()]
        self.closed = False
        self._closed = anyio.Event()

    def close(self) -> None:
        self.closed = True
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def start_serving(self) -> None:
        pass


class _FakeServerConnection:
    """Stands in for a server connection; tests override how it closes."""

    def announce_shutdown(self) -> None:
        pass

    def start_close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"ssl_handshake_timeout": "0"}, "must be positive"),
        ({"shutwait": "-1"}, "whole milliseconds"),
        ({"initial_window_size": str(2**31)}, "HTTP/2"),
    ],
    ids=["handshake-timeout", "shutwait", "http2-setting"],
)
def test_server_rejects_invalid_settings(parameters: dict[str, str], message: str, h2_url) -> None:
    async def handler(stream) -> None:
        raise AssertionError("no stream is opened")

    with pytest.raises(ValueError, match=message):
        AioH2Server(h2_url("127.0.0.1", 443, **parameters), handler)


async def test_server_maps_listener_failure(monkeypatch: pytest.MonkeyPatch, h2_url) -> None:
    async def fail_create_server(*args, **kwargs):
        raise OSError("address unavailable")

    async def handler(stream) -> None:
        raise AssertionError("the listener cannot create streams")

    server = AioH2Server(h2_url("127.0.0.1", 0), handler)
    monkeypatch.setattr(asyncio.get_running_loop(), "create_server", fail_create_server)

    with pytest.raises(OSError, match="address unavailable"):
        async with server:
            pass


async def test_server_rejects_multiple_ephemeral_listener_ports(monkeypatch: pytest.MonkeyPatch, h2_url) -> None:
    listener = _RecordingServer()
    listener.sockets = [
        _RecordingSocket(),
        _RecordingSocket("::1", 20_881),
    ]

    async def create_server(*args, **kwargs):
        return cast(asyncio.Server, listener)

    async def handler(stream) -> None:
        raise AssertionError("the fake listener cannot create streams")

    server = AioH2Server(h2_url("localhost", 0), handler)
    monkeypatch.setattr(asyncio.get_running_loop(), "create_server", create_server)

    with pytest.raises(ValueError, match="port 0 binds to different ports"):
        async with server:
            pass

    assert listener.closed


async def test_server_aclose_waits_for_each_connection_to_close(monkeypatch: pytest.MonkeyPatch, h2_url) -> None:
    listener = _RecordingServer()
    loop = asyncio.get_running_loop()

    async def create_server(*args, **kwargs):
        return cast(asyncio.Server, listener)

    async def handler(stream) -> None:
        raise AssertionError("the fake listener cannot create streams")

    server = AioH2Server(h2_url("127.0.0.1", 0), handler)
    monkeypatch.setattr(loop, "create_server", create_server)

    class SlowConnection(_FakeServerConnection):
        def __init__(self) -> None:
            self.closed = anyio.Event()

        async def aclose(self) -> None:
            loop.call_soon(self._finish_close)
            await self.closed.wait()

        def _finish_close(self) -> None:
            server._connections.discard(cast(AioH2Connection, self))
            self.closed.set()

    connection = SlowConnection()
    async with server:
        server._connections.add(cast(AioH2Connection, connection))
        await server.aclose()

    assert connection.closed.is_set()
    assert not server._connections
    assert listener.closed


async def test_server_aborts_a_connection_established_during_shutdown(h2_url, transport_type) -> None:
    async def handler(stream) -> None:
        raise AssertionError("no stream is opened")

    server = AioH2Server(h2_url("127.0.0.1", 0), handler)
    first_waiting = anyio.Event()
    release_first = anyio.Event()
    close_finished = anyio.Event()

    class GateConnection(_FakeServerConnection):
        async def aclose(self) -> None:
            first_waiting.set()
            await release_first.wait()
            server._connections.discard(cast(AioH2Connection, self))

    server._connections.add(cast(AioH2Connection, GateConnection()))

    async def close_server() -> None:
        await server.aclose()
        close_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(close_server)
        await first_waiting.wait()

        class AbortedTransport(transport_type):
            abort_calls = 0

            def abort(self) -> None:
                self.abort_calls += 1

        late = server._create_connection()
        transport = AbortedTransport()
        late.connection_made(transport)
        # Nothing else would close it, as the server owns only the connections it had.
        assert transport.abort_calls == 1
        assert late not in server._connections

        release_first.set()
        await close_finished.wait()
        late.connection_lost(None)

    assert not server._connections


async def test_closing_a_starting_server_retires_its_listener(monkeypatch: pytest.MonkeyPatch, h2_url) -> None:
    listener = _RecordingServer()
    created = anyio.Event()
    release = anyio.Event()

    async def create_server(*args, **kwargs):
        # The listener accepts nothing until the server owns it.
        assert kwargs["start_serving"] is False
        created.set()
        await release.wait()
        return cast(asyncio.Server, listener)

    async def handler(stream) -> None:
        raise AssertionError("the fake listener cannot create streams")

    monkeypatch.setattr(asyncio.get_running_loop(), "create_server", create_server)
    server = AioH2Server(h2_url("127.0.0.1", 0), handler)
    starting = asyncio.get_running_loop().create_task(server.__aenter__())
    await created.wait()

    await server.aclose()
    release.set()
    with pytest.raises(RuntimeError, match="closed while it started"):
        await starting

    assert listener.closed
    with pytest.raises(RuntimeError):
        await server.__aenter__()
