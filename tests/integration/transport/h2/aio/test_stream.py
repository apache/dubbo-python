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

import anyio
import pytest

from dubbo.transport.h2 import (
    H2ErrorCode,
    H2StreamResetError,
)
from dubbo.transport.h2.aio import AioH2Client, AioH2Server

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("body", "parameters"),
    [(b"answer", {}), (b"r" * (100 * 1024), {"initial_window_size": "65535"})],
    ids=["unbuffered", "flow-controlled"],
)
async def test_completing_a_response_preserves_its_body_and_stops_the_request(
    body, parameters, request_headers, response_headers, h2_url
):
    async def handler(stream):
        await stream.receive_headers()
        await stream.send_headers(response_headers)
        await stream.send_data(body)
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        async with (
            AioH2Client(h2_url(host, port, **parameters)) as client,
            await client.open_stream(request_headers) as stream,
        ):
            assert await stream.receive_headers() == response_headers
            assert await stream.receive_data_exactly(len(body)) == body
            assert await stream.receive_trailers() == ((b"grpc-status", b"0"),)

            async def send_until_reset():
                while True:
                    await stream.send_data(b"more")
                    await anyio.wait_all_tasks_blocked()

            with pytest.raises(H2StreamResetError, match="reset") as raised:
                await send_until_reset()

            assert raised.value.error_code == H2ErrorCode.NO_ERROR


async def test_a_request_outliving_a_flow_controlled_response_still_reaches_its_end(
    request_headers, response_headers, h2_url
) -> None:
    # The client's window holds part of the response when the handler returns.
    response = b"r" * (100 * 1024)

    async def handler(stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(response_headers)
        await stream.send_data(response)
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(h2_url("127.0.0.1", 0, initial_window_size="65535"), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port, initial_window_size="65535")) as client:
            stream = await client.open_stream(request_headers)
            async with stream:
                assert await stream.receive_headers() == response_headers

                # More than the server's stream window, which no handler reads anymore.
                with anyio.fail_after(5):
                    await stream.send_data(b"q" * (256 * 1024), end_stream=True)

                assert await stream.receive_data_exactly(len(response)) == response
                assert await stream.receive_trailers() == ((b"grpc-status", b"0"),)


async def test_a_send_blocked_when_a_complete_response_stops_the_request_raises(
    request_headers, response_headers, h2_url
) -> None:
    # RFC 9113 section 8.1: the request bytes still queued are discarded, so the send must not succeed.
    async def handler(stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(response_headers)
        await stream.send_data(b"answer")
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(h2_url("127.0.0.1", 0, initial_window_size="65535"), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            stream = await client.open_stream(request_headers)
            async with stream:
                # More than the server's stream window and the local send buffer together.
                with anyio.fail_after(5), pytest.raises(H2StreamResetError) as raised:
                    await stream.send_data(b"q" * (512 * 1024))
                assert raised.value.error_code == H2ErrorCode.NO_ERROR

                assert await stream.receive_headers() == response_headers
                assert await stream.receive_data_exactly(6) == b"answer"


async def test_h2c_round_trip_applies_flow_control_when_application_consumes_data(
    request_headers, response_headers, h2_url
) -> None:
    body = bytes(range(256)) * 1024
    prefix = b"\x00" + len(body).to_bytes(4, "big")

    async def handler(stream) -> None:
        assert await stream.receive_headers() == request_headers
        request_prefix = await stream.receive_data_exactly(5)
        request_body = await stream.receive_data_exactly(int.from_bytes(request_prefix[1:], "big"))
        assert await stream.receive_data() == b""

        await stream.send_headers(response_headers)
        await stream.send_data(request_prefix[:2])
        await stream.send_data(request_prefix[2:] + request_body, end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        async with (
            AioH2Client(h2_url(host, port)) as client,
            await client.open_stream(request_headers) as stream,
        ):
            await stream.send_data(prefix[:2])
            await stream.send_data(prefix[2:] + body, end_stream=True)

            assert await stream.receive_headers() == response_headers
            response_prefix = await stream.receive_data_exactly(5)
            response_body = await stream.receive_data_exactly(int.from_bytes(response_prefix[1:], "big"))
            assert response_prefix == prefix
            assert response_body == body
            assert await stream.receive_data() == b""


async def test_receive_data_exactly_returns_what_is_left_when_the_peer_ends(
    response_headers, h2_url, path_headers
) -> None:
    async def handler(stream) -> None:
        headers = await stream.receive_headers()
        if (b":path", b"/empty") in headers:
            await stream.send_headers(response_headers, end_stream=True)
            return

        await stream.send_headers(response_headers)
        await stream.send_data(b"abc", end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            empty = await client.open_stream(path_headers(b"/empty"), end_stream=True)
            assert await empty.receive_headers() == response_headers
            assert await empty.receive_data_exactly(1) == b""

            partial = await client.open_stream(path_headers(b"/partial"), end_stream=True)
            assert await partial.receive_headers() == response_headers
            assert await partial.receive_data_exactly(5) == b"abc"
            assert await partial.receive_data_exactly(5) == b""


async def test_stream_reset_does_not_close_the_connection(
    request_headers, response_headers, h2_url, path_headers
) -> None:
    async def handler(stream) -> None:
        headers = await stream.receive_headers()
        if (b":path", b"/reset") in headers:
            await stream.reset()
        else:
            await stream.send_headers(response_headers, end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            reset_stream = await client.open_stream(path_headers(b"/reset"), end_stream=True)
            with pytest.raises(H2StreamResetError) as raised:
                await reset_stream.receive_headers()
            assert raised.value.error_code == H2ErrorCode.CANCEL

            stream = await client.open_stream(request_headers, end_stream=True)
            assert await stream.receive_headers() == response_headers
            assert await stream.receive_data() == b""
            assert stream.stream_id == reset_stream.stream_id + 2


async def test_reset_returns_unread_data_to_the_connection_window(
    request_headers, response_headers, h2_url, path_headers
) -> None:
    body = b"x" * 40_000

    async def handler(stream) -> None:
        headers = await stream.receive_headers()
        if (b":path", b"/reset") in headers:
            # Waiting for the end of the request leaves its body unread.
            assert await stream.receive_trailers() is None
            await stream.reset()
            return

        assert await stream.receive_data_exactly(30_000) == b"y" * 30_000
        await stream.send_headers(response_headers, end_stream=True)

    # Smaller than both requests together, so the second needs the credit the reset returns.
    async with AioH2Server(h2_url("127.0.0.1", 0, connection_initial_window_size="65535"), handler) as server:
        host, port = server.address
        async with AioH2Client(h2_url(host, port)) as client:
            first = await client.open_stream(path_headers(b"/reset"))
            await first.send_data(body, end_stream=True)
            with pytest.raises(H2StreamResetError):
                await first.receive_headers()

            second = await client.open_stream(request_headers)
            await second.send_data(b"y" * 30_000, end_stream=True)
            assert await second.receive_headers() == response_headers


async def test_stream_context_releases_unread_response_data(
    request_headers, response_headers, h2_url, path_headers
) -> None:
    async def handler(stream) -> None:
        headers = await stream.receive_headers()
        await stream.send_headers(response_headers)
        if (b":path", b"/full-window") in headers:
            await stream.send_data(b"x" * (64 * 1024 - 1), end_stream=True)
        else:
            await stream.send_data(b"y", end_stream=True)

    async with AioH2Server(h2_url("127.0.0.1", 0), handler) as server:
        host, port = server.address
        # The protocol's smallest windows, which the first response fills.
        url = h2_url(host, port, initial_window_size="65535", connection_initial_window_size="65535")
        async with AioH2Client(url) as client:
            async with await client.open_stream(
                path_headers(b"/full-window"),
                end_stream=True,
            ) as first:
                assert await first.receive_headers() == response_headers
                # Waiting for the end of the response leaves its body unread.
                assert await first.receive_trailers() is None

            second = await client.open_stream(request_headers, end_stream=True)
            assert await second.receive_headers() == response_headers
            assert await second.receive_data() == b"y"
