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

import importlib.metadata

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo.protocol.triple import TripleProtocol
from dubbo.protocol.triple.grpc.framing import frame
from dubbo.protocol.triple.grpc.headers import decode_timeout
from dubbo.rpc.client import proxy
from dubbo.transport.h2 import H2Headers, H2Stream
from dubbo.transport.h2.aio import AioH2Server
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def _say(echo, request: StringValue) -> StringValue:
    return await echo.say(request)


async def _join(echo, request: StringValue) -> StringValue:
    async with echo.join() as stream:
        await stream.send(request)
        await stream.end()
        return await stream.receive()


@pytest.mark.parametrize("call", [_say, _join])
@pytest.mark.parametrize(("count", "problem"), [(0, "no message"), (3, "more than one message")])
async def test_a_call_of_one_response_takes_exactly_one(
    protocol: TripleProtocol,
    call,
    count: int,
    problem: str,
    echo_contract,
) -> None:
    async def respond(stream: H2Stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        for _ in range(count):
            await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo")
        echo = proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke)

        with pytest.raises(RpcError, match=f"the response has {problem}") as raised:
            await call(echo, StringValue(value="x"))
        # statuscodes.md:61
        assert raised.value.status is Status.UNIMPLEMENTED


async def test_a_call_names_the_library_in_its_user_agent(protocol: TripleProtocol, echo_contract) -> None:
    received: list[dict[bytes, bytes]] = []

    async def respond(stream: H2Stream) -> None:
        received.append(dict(await stream.receive_headers()))
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo")
        await proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke).say(
            StringValue(value="x")
        )

    version = importlib.metadata.version("apache-dubbo")
    assert received[0][b"user-agent"].startswith(f"grpc-python-dubbo/{version} (".encode())


async def test_a_call_sends_its_timeout_right_after_the_pseudo_headers(protocol: TripleProtocol, echo_contract) -> None:
    received: list[H2Headers] = []

    async def respond(stream: H2Stream) -> None:
        received.append(await stream.receive_headers())
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo")
        with anyio.fail_after(5):
            await proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke).say(
                StringValue(value="x")
            )

    # PROTOCOL-HTTP2.md:53
    names = [name for name, _ in received[0]]
    pseudo = sum(1 for name in names if name.startswith(b":"))
    assert names[pseudo] == b"grpc-timeout"


async def test_a_configured_timeout_is_the_grpc_timeout_of_the_call(protocol: TripleProtocol, echo_contract) -> None:
    received: list[dict[bytes, bytes]] = []

    async def respond(stream: H2Stream) -> None:
        received.append(dict(await stream.receive_headers()))
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo?timeout=50")
        with anyio.fail_after(5):
            await proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke).say(
                StringValue(value="x")
            )

    assert 0 < decode_timeout(received[0][b"grpc-timeout"]) <= 0.05


async def test_the_grpc_timeout_is_never_above_the_configured_timeout_whatever_the_clock_reads(
    protocol: TripleProtocol, echo_contract
) -> None:
    received: list[dict[bytes, bytes]] = []

    async def respond(stream: H2Stream) -> None:
        received.append(dict(await stream.receive_headers()))
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    # A reading where the timeout, added to it and taken away again, comes out a little larger, as it does for every
    # reading from 8 to 16.
    await anyio.sleep_until(8)
    now = anyio.current_time()
    assert (now + 0.05) - now > 0.05

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo?timeout=50")
        users = proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke)
        await users.say(StringValue(value="x"))

    assert decode_timeout(received[0][b"grpc-timeout"]) <= 0.05


async def test_an_explicit_grpc_status_decides_a_call_over_the_http_status(
    protocol: TripleProtocol, echo_contract
) -> None:
    async def respond(stream: H2Stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(
            (
                (b":status", b"500"),
                (b"content-type", b"application/grpc"),
                (b"grpc-status", b"10"),
                (b"grpc-message", b"aborted%20by%20provider"),
            ),
            end_stream=True,
        )

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo")
        echo = proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke)

        with pytest.raises(RpcError, match="aborted by provider") as raised:
            await echo.say(StringValue(value="x"))

    assert raised.value.status is Status.ABORTED


async def test_a_response_that_is_not_grpc_fails_whatever_grpc_status_it_carries(
    protocol: TripleProtocol, echo_contract
) -> None:
    async def respond(stream: H2Stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(
            ((b":status", b"200"), (b"content-type", b"text/html"), (b"grpc-status", b"0")), end_stream=True
        )

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo")
        echo = proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke)

        with pytest.raises(RpcError, match="content-type") as raised:
            await echo.say(StringValue(value="x"))

    assert raised.value.status is Status.UNKNOWN


async def test_a_compressing_caller_names_its_encoding_and_flags_its_messages(
    protocol: TripleProtocol, echo_contract
) -> None:
    received: list[tuple[dict[bytes, bytes], bytes]] = []

    async def respond(stream: H2Stream) -> None:
        headers = dict(await stream.receive_headers())
        received.append((headers, await stream.receive_data_exactly(5)))
        await stream.send_headers(((b":status", b"200"), (b"content-type", b"application/grpc+proto")))
        await stream.send_data(frame(StringValue(value="x").SerializeToString()))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server:
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Echo?triple.compressor=gzip")
        await proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke).say(
            StringValue(value="x")
        )

    headers, prefix = received[0]
    assert headers[b"grpc-encoding"] == b"gzip"
    assert prefix[0] == 1
