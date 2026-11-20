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
import socket
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import anyio
import ngh2
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream

from dubbo.transport.h2 import (
    H2ConnectionError,
)
from dubbo.transport.h2.aio import AioH2Client, AioH2Server
from dubbo.url import SSL_CONTEXT, URL

pytestmark = pytest.mark.anyio


async def test_tls_round_trip_negotiates_h2_for_a_domain_name(
    request_headers, response_headers, server_tls, client_tls, h2_url
) -> None:
    async def handler(stream) -> None:
        assert await stream.receive_headers() == request_headers
        await stream.send_headers(response_headers, end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0, **server_tls), handler) as server:
        _, port = server.address
        async with AioH2Client(h2_url("localhost", port, **client_tls)) as client:
            stream = await client.open_stream(request_headers, end_stream=True)
            assert await stream.receive_headers() == response_headers


async def test_a_given_server_context_without_h2_alpn_fails_the_connection_unchanged(
    request_headers, client_tls, certificates, h2_url
) -> None:
    async def handler(stream) -> None:
        await stream.reset()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificates / "localhost-cert.pem", certificates / "localhost-key.pem")
    url = h2_url("127.0.0.1", 0, ssl_enabled="true").replace(attributes={SSL_CONTEXT: context})

    async with AioH2Server(url, handler) as server:
        _, port = server.address
        async with AioH2Client(h2_url("localhost", port, **client_tls)) as client:
            with pytest.raises(H2ConnectionError, match="ALPN"):
                await client.open_stream(request_headers, end_stream=True)

    assert context.minimum_version == ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).minimum_version


def test_tls_round_trip_runs_on_uvloop(request_headers, response_headers, server_tls, client_tls, h2_url) -> None:
    uvloop = pytest.importorskip("uvloop")

    async def handler(stream) -> None:
        assert await stream.receive_headers() == request_headers
        await stream.send_headers(response_headers, end_stream=True)

    async def round_trip() -> None:
        async with AioH2Server(h2_url("127.0.0.1", 0, **server_tls), handler) as server:
            _, port = server.address
            async with AioH2Client(h2_url("localhost", port, **client_tls)) as client:
                stream = await client.open_stream(request_headers, end_stream=True)
                assert await stream.receive_headers() == response_headers

    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(asyncio.wait_for(round_trip(), 10))


async def test_tls_certificate_failure_maps_to_h2_connection_error(request_headers, server_tls, h2_url) -> None:
    async def handler(stream) -> None:
        await stream.reset()

    async with AioH2Server(h2_url("127.0.0.1", 0, **server_tls), handler) as server:
        _, port = server.address
        async with AioH2Client(h2_url("localhost", port, ssl_enabled="true")) as client:
            with pytest.raises(H2ConnectionError) as raised:
                await client.open_stream(request_headers, end_stream=True)

        assert isinstance(raised.value.__cause__, ssl.SSLCertVerificationError)


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
async def test_h2c_round_trip_over_ipv6(request_headers, response_headers, h2_url) -> None:
    async def handler(stream) -> None:
        assert await stream.receive_headers() == request_headers
        await stream.send_headers(response_headers, end_stream=True)

    async with AioH2Server(h2_url("::1", 0), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            stream = await client.open_stream(request_headers, end_stream=True)
            assert await stream.receive_headers() == response_headers


async def test_keep_alive_ping_is_acknowledged_on_an_idle_connection(request_headers, response_headers, h2_url):
    acknowledged = anyio.Event()

    async def handler(stream):
        await stream.receive_headers()
        await stream.send_headers(response_headers, end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address

        async def proxy(stream):
            async def relay(source, target, preface=False):
                reader = BufferedByteReceiveStream(source)
                if preface:
                    await target.send(await reader.receive_exactly(24))
                while True:
                    header = await reader.receive_exactly(9)
                    payload = await reader.receive_exactly(int.from_bytes(header[:3], "big"))
                    await target.send(header + payload)
                    if not preface and header[3:5] == b"\x06\x01" and payload == (1).to_bytes(8, "big"):
                        acknowledged.set()

            async with stream, await anyio.connect_tcp(host, port) as upstream, anyio.create_task_group() as pipes:
                pipes.start_soon(relay, stream, upstream, True)
                pipes.start_soon(relay, upstream, stream)

        async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener:
            proxy_port = listener.extra(anyio.abc.SocketAttribute.local_port)
            async with (
                AioH2Client(h2_url(host, proxy_port, keep_alive_interval="10", keep_alive_timeout="1000")) as client,
                anyio.create_task_group() as tasks,
            ):
                tasks.start_soon(listener.serve, proxy)
                stream = await client.open_stream(request_headers, end_stream=True)
                assert await stream.receive_headers() == response_headers

                await acknowledged.wait()

                next_stream = await client.open_stream(request_headers, end_stream=True)
                assert await next_stream.receive_headers() == response_headers
                assert next_stream.stream_id == stream.stream_id + 2
                tasks.cancel_scope.cancel()


async def test_a_response_finished_after_the_peer_goaway_is_written_before_the_socket_closes(
    request_headers, response_headers, h2_url
) -> None:
    async def handler(stream) -> None:
        await stream.receive_headers()
        # The request ends after the client's GOAWAY, so the server reads that GOAWAY first.
        assert await stream.receive_data() == b""
        await stream.send_headers(response_headers)
        await stream.send_data(b"last", end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        client = AioH2Client(h2_url(host, port))
        stream = await client.open_stream(request_headers)
        async with anyio.create_task_group() as task_group:
            # Closing the client sends GOAWAY while its stream still waits for the response.
            task_group.start_soon(client.aclose)
            await anyio.wait_all_tasks_blocked()
            await stream.end()

            # Writing the last response also closes the server's last stream.
            assert await stream.receive_headers() == response_headers
            assert await stream.receive_data() == b"last"


async def test_completed_stream_remains_readable_after_final_goaway(request_headers, response_headers) -> None:
    async def respond(engine: ngh2.Connection, request: ngh2.RequestReceived, peer: anyio.abc.SocketStream) -> None:
        engine.send_shutdown_notice()
        engine.send_goaway(last_stream_id=request.stream_id)
        engine.send_response(request.stream_id, response_headers)
        engine.send_data(request.stream_id, b"payload", end_stream=True)

    async with _raw_server(respond) as (url, client_closed), AioH2Client(url) as client:
        stream = await client.open_stream(request_headers, end_stream=True)
        assert await stream.receive_headers() == response_headers
        # The client closes its socket once the GOAWAY has ended its last stream.
        await client_closed.wait()

        assert await stream.receive_data() == b"payload"
        assert await stream.receive_data() == b""


async def test_socket_failure_maps_to_h2_connection_error(request_headers, h2_url) -> None:
    class AbortOnData(asyncio.Protocol):
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            self.transport = transport

        def data_received(self, data: bytes) -> None:
            self.transport.abort()

    async def open_then_receive(client: AioH2Client) -> None:
        stream = await client.open_stream(request_headers, end_stream=True)
        await stream.receive_headers()

    loop = asyncio.get_running_loop()
    async with await loop.create_server(AbortOnData, "127.0.0.1", 0) as server:
        address = server.sockets[0].getsockname()
        async with AioH2Client(h2_url(address[0], address[1])) as client:
            with pytest.raises(H2ConnectionError):
                await open_then_receive(client)


async def test_a_stream_above_the_goaway_last_stream_id_fails_with_the_connection(
    response_headers, path_headers
) -> None:
    release_first = anyio.Event()
    first_ids: list[int] = []

    async def respond(engine: ngh2.Connection, request: ngh2.RequestReceived, peer: anyio.abc.SocketStream) -> None:
        if (b":path", b"/first") in request.headers:
            first_ids.append(request.stream_id)
            return

        engine.send_goaway(last_stream_id=request.stream_id - 2)
        await peer.send(engine.data_to_send())
        await release_first.wait()
        engine.send_response(first_ids[0], response_headers, end_stream=True)

    async with _raw_server(respond) as (url, _), AioH2Client(url) as client:
        first = await client.open_stream(path_headers(b"/first"), end_stream=True)
        second = await client.open_stream(path_headers(b"/second"), end_stream=True)

        with anyio.fail_after(5), pytest.raises(H2ConnectionError, match="draining"):
            await second.receive_headers()

        release_first.set()
        assert await first.receive_headers() == response_headers


@asynccontextmanager
async def _raw_server(
    respond: Callable[[ngh2.Connection, ngh2.RequestReceived, anyio.abc.SocketStream], Awaitable[None]],
    settings: dict[ngh2.Setting, int] | None = None,
) -> AsyncIterator[tuple[URL, anyio.Event]]:
    """Serve one client from a bare ngh2 engine that ``respond`` drives for each request, announcing ``settings``.

    Yield the URL to connect to and an event set once the client closes its socket.
    """
    client_closed = anyio.Event()

    async def serve(peer: anyio.abc.SocketStream) -> None:
        engine = ngh2.Connection(ngh2.Role.SERVER)
        engine.initiate_connection(settings)
        async with peer:
            await peer.send(engine.data_to_send())
            async for data in peer:
                # A terminated engine reads nothing more, but the client may still write before closing.
                if not engine.want_read:
                    continue
                engine.receive_data(data)
                for event in engine.events():
                    if isinstance(event, ngh2.RequestReceived):
                        await respond(engine, event, peer)
                if outgoing := engine.data_to_send():
                    await peer.send(outgoing)
        client_closed.set()

    async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener, anyio.create_task_group() as tasks:
        tasks.start_soon(listener.serve, serve)
        port = listener.extra(anyio.abc.SocketAttribute.local_port)
        yield URL(protocol="tri", host="127.0.0.1", port=port), client_closed
        tasks.cancel_scope.cancel()


@asynccontextmanager
async def _one_stream_at_a_time(
    h2_url, response_headers
) -> AsyncIterator[tuple[AioH2Client, list[bytes], anyio.Event]]:
    """Yield a client of a server that serves one stream at a time, the paths it served, and what ends ``/held``."""
    served: list[bytes] = []
    release = anyio.Event()

    async def handler(stream) -> None:
        path = dict(await stream.receive_headers())[b":path"]
        served.append(path)
        if path == b"/held":
            await release.wait()
        await stream.send_headers(response_headers)
        await stream.send_data(b"", end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0, max_concurrent_streams="1"), handler) as server:
        _, port = server.address
        async with AioH2Client(h2_url("127.0.0.1", port)) as client:
            yield client, served, release


async def test_streams_open_in_the_order_they_waited_for_room(path_headers, response_headers, h2_url) -> None:
    async with _one_stream_at_a_time(h2_url, response_headers) as (client, served, release):
        held = await client.open_stream(path_headers(b"/held"), end_stream=True)
        await anyio.wait_all_tasks_blocked()

        async def call(path: bytes) -> None:
            stream = await client.open_stream(path_headers(path), end_stream=True)
            await stream.receive_headers()
            await stream.receive_data()

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(call, b"/waited")
                await anyio.wait_all_tasks_blocked()
                release.set()
                await held.receive_headers()
                await held.receive_data()
                # Arriving once the held stream closes, it still comes after the one that waited.
                await call(b"/later")

    assert served == [b"/held", b"/waited", b"/later"]


@pytest.mark.parametrize("settings", [{ngh2.Setting.MAX_CONCURRENT_STREAMS: 3}, {}], ids=["announced", "unlimited"])
async def test_a_client_opens_as_many_streams_as_the_server_allows(path_headers, settings) -> None:
    held: list[int] = []

    async def respond(engine: ngh2.Connection, request: ngh2.RequestReceived, peer: anyio.abc.SocketStream) -> None:
        held.append(request.stream_id)

    # Its own limit is what the server may open towards it, not what it opens.
    async with (
        _raw_server(respond, settings) as (url, _),
        AioH2Client(url.update_parameters({"max-concurrent-streams": "1"})) as client,
    ):
        with anyio.fail_after(5):
            streams = [await client.open_stream(path_headers(b"/held"), end_stream=True) for _ in range(3)]
            while len(held) < 3:
                await anyio.sleep(0.01)

    assert len(streams) == 3


async def test_streams_open_in_the_order_they_waited_when_the_peer_lowers_its_limit(path_headers) -> None:
    held: list[int] = []
    served: list[bytes] = []
    release = anyio.Event()

    async def respond(engine: ngh2.Connection, request: ngh2.RequestReceived, peer: anyio.abc.SocketStream) -> None:
        if len(held) == 2:
            served.append(dict(request.headers)[b":path"])
            engine.send_response(request.stream_id, ((b":status", b"200"),), end_stream=True)
            return

        held.append(request.stream_id)
        if len(held) == 2:
            await release.wait()
            # Both held streams end, then the limit falls to one, in one write.
            for stream_id in held:
                engine.send_response(stream_id, ((b":status", b"200"),), end_stream=True)
            responses = engine.data_to_send()
            engine.update_settings({ngh2.Setting.MAX_CONCURRENT_STREAMS: 1})
            await peer.send(responses + engine.data_to_send())

    async def call(path: bytes) -> None:
        stream = await client.open_stream(path_headers(path), end_stream=True)
        await stream.receive_headers()

    async with (
        _raw_server(respond, {ngh2.Setting.MAX_CONCURRENT_STREAMS: 2}) as (url, _),
        AioH2Client(url) as client,
    ):
        streams = [await client.open_stream(path_headers(b"/held"), end_stream=True) for _ in range(2)]
        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(call, b"/first")
                await anyio.wait_all_tasks_blocked()
                tasks.start_soon(call, b"/second")
                await anyio.wait_all_tasks_blocked()
                release.set()
            for stream in streams:
                await stream.receive_headers()

    assert served == [b"/first", b"/second"]


async def test_a_waiter_cancelled_before_its_turn_leaves_the_room_to_the_next(
    path_headers, response_headers, h2_url
) -> None:
    async with _one_stream_at_a_time(h2_url, response_headers) as (client, served, release):
        held = await client.open_stream(path_headers(b"/held"), end_stream=True)
        await anyio.wait_all_tasks_blocked()
        opened: list[bytes] = []

        async def call(path: bytes) -> None:
            stream = await client.open_stream(path_headers(path), end_stream=True)
            opened.append(path)
            await stream.receive_headers()
            await stream.receive_data()

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                first = anyio.CancelScope()

                async def cancellable() -> None:
                    with first:
                        await call(b"/cancelled")

                tasks.start_soon(cancellable)
                await anyio.wait_all_tasks_blocked()
                tasks.start_soon(call, b"/next")
                await anyio.wait_all_tasks_blocked()
                first.cancel()
                release.set()
                await held.receive_headers()
                await held.receive_data()

    assert opened == [b"/next"]
    assert served == [b"/held", b"/next"]
