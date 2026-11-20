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

import gc

import anyio
import pytest

import dubbo.utils.async_ as async_module
from dubbo.transport.h2 import (
    H2ConnectionError,
)
from dubbo.transport.h2.aio import AioH2Client, AioH2Server

pytestmark = pytest.mark.anyio


async def test_connect_timeout_bounds_a_stalled_handshake_and_waiting_callers_share_its_failure(
    request_headers, client_tls, h2_url
) -> None:
    accepted: list[anyio.abc.SocketStream] = []

    async def withhold_handshake(stream: anyio.abc.SocketStream) -> None:
        accepted.append(stream)
        async with stream:
            await anyio.sleep_forever()

    listener = await anyio.create_tcp_listener(local_host="127.0.0.1")
    port = listener.extra(anyio.abc.SocketAttribute.local_port)
    client = AioH2Client(h2_url("127.0.0.1", port, connect_timeout="100", **client_tls))

    async def open_stream() -> None:
        with pytest.raises(H2ConnectionError, match="failed to connect"):
            await client.open_stream(request_headers, end_stream=True)

    async with listener, anyio.create_task_group() as server:
        server.start_soon(listener.serve, withhold_handshake)
        with anyio.fail_after(5):
            async with anyio.create_task_group() as callers:
                callers.start_soon(open_stream)
                callers.start_soon(open_stream)

        assert len(accepted) == 1
        assert not client.available
        await client.aclose()
        server.cancel_scope.cancel()


async def test_client_closed_while_connecting_releases_its_socket(h2_url) -> None:
    listener = await anyio.create_tcp_listener(local_host="127.0.0.1")
    port = listener.extra(anyio.abc.SocketAttribute.local_port)

    async with listener:
        # The attempt is cancelled at each step it can reach before the close.
        for steps in range(20):
            client = await AioH2Client(h2_url("127.0.0.1", port)).__aenter__()
            for _ in range(steps % 5):
                await anyio.sleep(0)
            await client.aclose()

    # A socket left open warns as it is collected, which fails the test.
    gc.collect()


async def test_cancelling_a_client_close_aborts_its_connections_at_once(request_headers, h2_url) -> None:
    async def handler(stream) -> None:
        await stream.receive_headers()
        await anyio.sleep_forever()

    async with AioH2Server(h2_url("127.0.0.1", 0, shutwait="0"), handler) as server:
        host, port = server.address
        client = AioH2Client(h2_url(host, port))
        stream = await client.open_stream(request_headers)
        connection = client._active_connection
        assert connection is not None

        started = anyio.current_time()
        with anyio.move_on_after(0.02):
            await client.aclose()

        # The open stream would hold a graceful close for its grace period of a second.
        assert anyio.current_time() - started == pytest.approx(0.02)
        assert connection.closed
        with pytest.raises(H2ConnectionError):
            await stream.receive_headers()


async def test_client_close_waits_for_its_connections_together(
    monkeypatch: pytest.MonkeyPatch, request_headers, response_headers, h2_url
) -> None:
    monkeypatch.setattr(async_module, "_CLOSE_GRACE", 0.2)

    async def handler(stream) -> None:
        await stream.receive_headers()
        # The client reads the GOAWAY before these headers, so its next stream opens another connection.
        server.announce_shutdown()
        await stream.send_headers(response_headers)
        await anyio.sleep_forever()

    async with AioH2Server(h2_url("127.0.0.1", 0, shutwait="0"), handler) as server:
        host, port = server.address
        client = AioH2Client(h2_url(host, port))
        streams = []
        for _ in range(3):
            streams.append(await client.open_stream(request_headers))
            await streams[-1].receive_headers()
        # Two draining after a GOAWAY, and the active one.
        assert len(client._draining_connections) == 2

        started = anyio.current_time()
        await client.aclose()

        # One after another, the three open streams would hold the close for three grace periods.
        assert anyio.current_time() - started == pytest.approx(0.2)


async def test_client_replaces_a_connection_draining_after_goaway(response_headers, h2_url, path_headers) -> None:
    release_old_stream = anyio.Event()
    peers: dict[bytes, str | None] = {}

    async def handler(stream) -> None:
        headers = await stream.receive_headers()
        path = dict(headers)[b":path"]
        peers[path] = stream.peer
        if path == b"/old":
            server.announce_shutdown()
            # The client reads the GOAWAY before these headers, which follow it on the connection.
            await stream.send_headers(response_headers)
            await release_old_stream.wait()
            await stream.end()
            return

        await stream.send_headers(response_headers, end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            old_stream = await client.open_stream(path_headers(b"/old"), end_stream=True)
            assert await old_stream.receive_headers() == response_headers

            new_stream = await client.open_stream(path_headers(b"/new"), end_stream=True)
            assert await new_stream.receive_headers() == response_headers
            assert new_stream.stream_id == 1

            release_old_stream.set()
            assert await old_stream.receive_data() == b""
            assert peers[b"/old"] != peers[b"/new"]
