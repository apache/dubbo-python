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
from typing import cast

import anyio
import ngh2
import pytest

import dubbo.utils.dialer as dialer_module
from dubbo.extension import extensions
from dubbo.transport.h2 import (
    H2Client,
    H2ConnectionError,
    H2Server,
)
from dubbo.transport.h2.aio import AioH2Client, AioH2Server, AioH2Stream
from dubbo.transport.h2.aio.connection import AioH2Connection
from dubbo.url import URL

pytestmark = pytest.mark.anyio

# An empty SETTINGS frame, with which a server starts its connection preface.
_SERVER_SETTINGS = b"\x00\x00\x00\x04\x00\x00\x00\x00\x00"


def _answer(connection: AioH2Connection) -> None:
    """Deliver the preface of a server that answers, which the client waits for before using the connection."""
    connection.get_buffer(len(_SERVER_SETTINGS))[: len(_SERVER_SETTINGS)] = _SERVER_SETTINGS
    connection.buffer_updated(len(_SERVER_SETTINGS))


# Only the addresses of a host name are raced; an IP address is one.
@pytest.mark.parametrize(
    ("host", "server_name", "checked", "race"),
    [
        ("provider.example", "service.example", "service.example", {"happy_eyeballs_delay": 0.25}),
        ("192.0.2.1", "", "192.0.2.1", {}),
    ],
    ids=["named", "empty-checks-host"],
)
async def test_client_passes_tls_identity_and_happy_eyeballs_to_asyncio(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, tls_transport_type, host, server_name, checked, race
) -> None:
    captured: dict[str, object] = {}

    async def create_connection(protocol_factory, host, port, **kwargs):
        captured.update(host=host, port=port, **kwargs)
        connection = protocol_factory()
        transport = tls_transport_type("h2")
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_connection", create_connection)
    client = AioH2Client(h2_url(host, 443, ssl_enabled="true", tls_server_name=server_name))
    stream = await client.open_stream(request_headers, end_stream=True)
    context = captured["ssl"]
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert context.options & ssl.OP_NO_COMPRESSION
    assert context.options & ssl.OP_NO_RENEGOTIATION

    assert stream.stream_id == 1
    assert captured == {
        "host": host,
        "port": 443,
        "ssl": context,
        "server_hostname": checked,
        **race,
    }
    connection = client._active_connection
    assert connection is not None
    connection.connection_lost(None)
    await client.aclose()


def test_aio_is_the_default_client_and_server() -> None:
    assert extensions.get(H2Client, None) is AioH2Client
    assert extensions.get(H2Server, None) is AioH2Server


def test_client_requires_a_host_and_port() -> None:
    with pytest.raises(ValueError, match="host and a port"):
        AioH2Client(URL(protocol="tri", host="127.0.0.1"))


async def test_client_reports_alpn_failure_without_reconnecting(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, tls_transport_type
) -> None:
    attempts = 0

    async def create_connection(protocol_factory, host, port, **kwargs):
        nonlocal attempts
        attempts += 1
        connection = protocol_factory()

        class RejectingTransport(tls_transport_type):
            def abort(self) -> None:
                self.abort_calls += 1
                connection.connection_lost(None)

        transport = RejectingTransport(None)
        connection.connection_made(transport)
        return transport, connection

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_connection", create_connection)
    client = AioH2Client(h2_url("service.example", 443, ssl_enabled="true"))

    with pytest.raises(H2ConnectionError, match="ALPN"):
        await client.open_stream(request_headers, end_stream=True)

    assert attempts == 1
    # Nothing public shows that the client let go of its connection.
    assert client._active_connection is None
    await client.aclose()


async def test_caller_that_stops_waiting_leaves_the_attempt_to_the_others(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, transport_type
) -> None:
    started = anyio.Event()
    release = anyio.Event()
    attempts = 0

    async def slow_create_connection(protocol_factory, host, port, **kwargs):
        nonlocal attempts
        attempts += 1
        started.set()
        await release.wait()
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_connection", slow_create_connection)
    client = AioH2Client(h2_url("127.0.0.1", 1))

    with anyio.move_on_after(0.01):
        await client.open_stream(request_headers, end_stream=True)
    await started.wait()
    # The attempt runs on.
    assert client._dialer._attempt is not None

    release.set()
    stream = await client.open_stream(request_headers, end_stream=True)

    assert attempts == 1
    assert stream.stream_id == 1
    assert client.available
    connection = client._active_connection
    assert connection is not None
    connection.connection_lost(None)
    await client.aclose()


async def test_an_unanswered_attempt_fails_at_the_connect_timeout_and_leaves_the_client_unavailable(
    monkeypatch: pytest.MonkeyPatch, h2_url
) -> None:
    attempts = 0

    async def unanswered_create_connection(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        await anyio.sleep_forever()

    monkeypatch.setattr(asyncio.get_running_loop(), "create_connection", unanswered_create_connection)
    # No retry within the test, so that the state after the failure stays.
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([60.0] * 3))
    async with AioH2Client(h2_url("127.0.0.1", 1, connect_timeout="50")) as client:
        # Only the connect timeout ends the attempt; the bound only keeps a broken timeout from hanging.
        with anyio.fail_after(5):
            while client._dialer._attempt is not None:
                await anyio.sleep(0.01)

        assert (attempts, client.available) == (1, False)


async def test_entered_client_connects_and_reconnects_in_the_background(
    monkeypatch: pytest.MonkeyPatch, h2_url, transport_type
) -> None:
    connections: list[AioH2Connection] = []

    async def create_connection(protocol_factory, host, port, **kwargs):
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        connections.append(connection)
        return transport, connection

    async def until(condition) -> None:
        with anyio.fail_after(5):
            while not condition():
                await anyio.sleep(0.001)

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_connection", create_connection)
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.01] * 3))
    async with AioH2Client(h2_url("127.0.0.1", 1)) as client:
        await until(lambda: connections)
        assert client.available

        connections[0].connection_lost(None)
        assert not client.available
        await until(lambda: len(connections) == 2 and client.available)

        connections[1].connection_lost(None)


async def test_concurrent_streams_wait_for_connection_establishment(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, transport_type
) -> None:
    dial_started = anyio.Event()
    release_dial = anyio.Event()
    second_opened = anyio.Event()
    streams: list[AioH2Stream] = []
    attempts = 0
    loop = asyncio.get_running_loop()

    async def delayed_create_connection(protocol_factory, host, port, **kwargs):
        nonlocal attempts
        attempts += 1
        dial_started.set()
        await release_dial.wait()
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    monkeypatch.setattr(loop, "create_connection", delayed_create_connection)
    client = AioH2Client(h2_url("127.0.0.1", 1))

    async def open_stream(signal: anyio.Event | None = None) -> None:
        streams.append(await client.open_stream(request_headers, end_stream=True))
        if signal is not None:
            signal.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(open_stream)
        await dial_started.wait()
        task_group.start_soon(open_stream, second_opened)
        await anyio.wait_all_tasks_blocked()

        assert not second_opened.is_set()
        assert not streams

        release_dial.set()

    assert attempts == 1
    assert {stream.stream_id for stream in streams} == {1, 3}
    connection = client._active_connection
    assert connection is not None
    connection.connection_lost(None)
    await client.aclose()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_client_rejects_a_connect_timeout_that_is_not_positive(value: str, h2_url) -> None:
    with pytest.raises(ValueError, match="connect-timeout"):
        AioH2Client(h2_url("127.0.0.1", 1, connect_timeout=value))


async def test_client_is_available_only_while_it_is_connected(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, transport_type
) -> None:
    refuse = True
    attempts = 0
    loop = asyncio.get_running_loop()

    async def create_connection(protocol_factory, host, port, **kwargs):
        nonlocal attempts
        attempts += 1
        if refuse:
            raise ConnectionRefusedError
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    async def until(condition) -> None:
        with anyio.fail_after(5):
            while not condition():
                await anyio.sleep(0.001)

    monkeypatch.setattr(loop, "create_connection", create_connection)
    # Each failure in a row waits the next delay; a success starts them again.
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.01, 60.0]))
    client = AioH2Client(h2_url("127.0.0.1", 1))
    # Nothing is connected before the first attempt succeeds.
    assert not client.available

    with pytest.raises(H2ConnectionError, match="failed to connect"):
        await client.open_stream(request_headers, end_stream=True)
    assert not client.available
    # The attempt after the first delay fails too, and the next waits the second.
    await until(lambda: attempts == 2)
    assert not client.available

    # Opening a stream still connects while the client is unavailable.
    refuse = False
    await client.open_stream(request_headers, end_stream=True)
    assert client.available

    # A lost connection waits the first delay again before the client connects in the background.
    connection = client._active_connection
    assert connection is not None
    connection.connection_lost(None)
    assert not client.available
    await until(lambda: client.available)
    assert attempts == 4

    connection = client._active_connection
    assert connection is not None
    connection.connection_lost(None)
    await client.aclose()
    assert not client.available


async def test_client_aclose_abandons_an_inflight_connection_attempt(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url
) -> None:
    create_started = anyio.Event()
    loop = asyncio.get_running_loop()

    async def stalled_create_connection(protocol_factory, host, port, **kwargs):
        # As a dial to an unreachable address, which only the operating system would end.
        create_started.set()
        await anyio.sleep_forever()

    client = AioH2Client(h2_url("127.0.0.1", 1))
    monkeypatch.setattr(loop, "create_connection", stalled_create_connection)

    async def open_stream() -> None:
        with pytest.raises(RuntimeError, match="closed"):
            await client.open_stream(request_headers, end_stream=True)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(open_stream)
        await create_started.wait()
        with anyio.fail_after(5):
            await client.aclose()

    # Nothing public shows that the client let go of its connections.
    assert client._active_connection is None
    assert not client._draining_connections


async def test_concurrent_client_close_waits_for_connection_cleanup(h2_url) -> None:
    started = anyio.Event()
    release = anyio.Event()

    class DelayedConnection:
        def start_close(self) -> None:
            pass

        async def aclose(self) -> None:
            started.set()
            await release.wait()

    client = AioH2Client(h2_url("127.0.0.1", 1))
    client._active_connection = cast(AioH2Connection, DelayedConnection())
    first_done = anyio.Event()
    second_done = anyio.Event()

    async def close(done: anyio.Event) -> None:
        await client.aclose()
        done.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(close, first_done)
        await started.wait()
        task_group.start_soon(close, second_done)
        await anyio.wait_all_tasks_blocked()
        assert not second_done.is_set()
        release.set()
        await first_done.wait()
        await second_done.wait()


async def test_client_aclose_inside_a_cancelled_scope_aborts_its_connection(
    h2_url, connection_url, transport_type
) -> None:
    client = AioH2Client(h2_url("127.0.0.1", 1))
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url(), on_closed=client._connection_closed)
    loop = asyncio.get_running_loop()

    class AbortingTransport(transport_type):
        def abort(self) -> None:
            loop.call_soon(connection.connection_lost, None)

    connection.connection_made(AbortingTransport())
    client._active_connection = connection

    with anyio.CancelScope() as scope:
        scope.cancel()
        await client.aclose()

    assert connection.closed
    # Nothing public shows that the client let go of its connection.
    assert client._active_connection is None


async def test_client_reselects_when_goaway_arrives_during_capacity_wait(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, connection_url, transport_type
) -> None:
    config = connection_url(max_concurrent_streams=1)
    client = AioH2Client(h2_url("127.0.0.1", 1, max_concurrent_streams="1"))
    old_connection = AioH2Connection(
        ngh2.Role.CLIENT,
        url=config,
        on_closed=client._connection_closed,
    )
    old_connection.connection_made(transport_type())
    old_connection._streams_by_id[1] = AioH2Stream(old_connection, 1, headers_sent=True)
    client._active_connection = old_connection
    assert old_connection.accepting_streams

    loop = asyncio.get_running_loop()

    async def create_connection(protocol_factory, host, port, **kwargs):
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    monkeypatch.setattr(loop, "create_connection", create_connection)
    opened: list[AioH2Stream] = []

    async def open_stream() -> None:
        opened.append(await client.open_stream(request_headers, end_stream=True))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(open_stream)
        await anyio.wait_all_tasks_blocked()
        assert not opened

        old_connection._draining = True
        old_connection._notify_capacity()

    new_connection = client._active_connection
    assert new_connection is not None
    assert new_connection is not old_connection
    assert opened[0].stream_id == 1

    old_connection.connection_lost(None)
    new_connection.connection_lost(None)
    await client.aclose()


async def test_client_reselects_when_connection_fails_during_capacity_wait(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, connection_url, transport_type
) -> None:
    config = connection_url(max_concurrent_streams=1)
    client = AioH2Client(h2_url("127.0.0.1", 1, max_concurrent_streams="1"))
    old_connection = AioH2Connection(
        ngh2.Role.CLIENT,
        url=config,
        on_closed=client._connection_closed,
    )

    class AbortTransport(transport_type):
        def abort(self) -> None:
            old_connection.connection_lost(None)

    old_connection.connection_made(AbortTransport())
    old_connection._streams_by_id[1] = AioH2Stream(old_connection, 1, headers_sent=True)
    client._active_connection = old_connection

    loop = asyncio.get_running_loop()

    async def create_connection(protocol_factory, host, port, **kwargs):
        connection = protocol_factory()
        transport = transport_type()
        connection.connection_made(transport)
        _answer(connection)
        return transport, connection

    monkeypatch.setattr(loop, "create_connection", create_connection)
    opened: list[AioH2Stream] = []

    async def open_stream() -> None:
        opened.append(await client.open_stream(request_headers, end_stream=True))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(open_stream)
        await anyio.wait_all_tasks_blocked()
        assert not opened

        old_connection._fail_connection(H2ConnectionError("connection lost"))
        old_connection.abort()

    new_connection = client._active_connection
    assert new_connection is not None
    assert new_connection is not old_connection
    assert opened[0].stream_id == 1

    new_connection.connection_lost(None)
    await client.aclose()


async def test_client_limits_reselection_before_stream_allocation(
    monkeypatch: pytest.MonkeyPatch, request_headers, h2_url, transport_type
) -> None:
    attempts: list[AioH2Connection] = []
    loop = asyncio.get_running_loop()

    async def create_connection(protocol_factory, host, port, **kwargs):
        connection = protocol_factory()

        class ClosingTransport(transport_type):
            def close(self) -> None:
                super().close()
                connection.connection_lost(None)

        transport = ClosingTransport()
        connection.connection_made(transport)
        _answer(connection)
        connection._draining = True
        attempts.append(connection)
        return transport, connection

    monkeypatch.setattr(loop, "create_connection", create_connection)
    client = AioH2Client(h2_url("127.0.0.1", 1))

    with pytest.raises(H2ConnectionError, match="unavailable before opening"):
        await client.open_stream(request_headers, end_stream=True)

    assert len(attempts) == 2
    await client.aclose()
