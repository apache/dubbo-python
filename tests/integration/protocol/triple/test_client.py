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

import math
import socket
from collections.abc import AsyncIterator

import anyio
import grpc
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo._proto.google.rpc.status_pb2 import Status as StatusMessage
from dubbo.protocol.triple import TripleError, TripleProtocol
from dubbo.rpc.client import proxy
from dubbo.url import URL

pytestmark = pytest.mark.anyio

# grpcio calls through threads of its own and keeps its deadlines on the real clock.
_grpcio = pytest.mark.real_clock


async def test_unary_carries_attachments_both_ways(echo) -> None:
    with dubbo.outgoing({"Tenant": "t1"}) as call:
        assert await echo.say(StringValue(value="hi")) == StringValue(value="hi|t1")

    assert dict(call.response_attachments) == {"Served-By": "echo"}


async def test_calls_attach_the_token_of_the_provider(protocol: TripleProtocol, impl, export, refer) -> None:
    guarded = await refer(protocol, await export(protocol, impl), "?token=secret")

    with dubbo.outgoing() as call:
        await guarded.say(StringValue(value="hi"))

    assert call.response_attachments.getall("token") == ["secret"]


@pytest.mark.parametrize("query", ["?token=secret", ""], ids=["with-token", "without-token"])
async def test_a_call_may_not_attach_a_token(protocol: TripleProtocol, impl, export, refer, query) -> None:
    echo = await refer(protocol, await export(protocol, impl), query)
    # Connected first, as the refused call never waits for it: a server that closes while a client connects
    # leaves the socket to the garbage collector in CPython.
    await echo.say(StringValue(value="hi"))

    with dubbo.outgoing({"token": "mine"}), pytest.raises(RpcError) as caught:
        await echo.say(StringValue(value="hi"))

    assert caught.value.status is Status.INVALID_ARGUMENT


async def test_an_unknown_compressor_fails_the_reference(protocol: TripleProtocol, impl, export, refer) -> None:
    exporter = await export(protocol, impl)

    with pytest.raises(ValueError, match="'compressor'"):
        await refer(protocol, exporter, "?triple.compressor=snappy")


async def test_a_request_over_the_servers_limit_is_resource_exhausted(protocol, impl, export, refer):
    echo = await refer(protocol, await export(protocol, impl, "?triple.max-receive-message-size=8"))
    assert await echo.say(StringValue(value="hi")) == StringValue(value="hi|-")

    with pytest.raises(RpcError, match="larger than 8") as raised:
        await echo.say(StringValue(value="longer than eight"))

    assert raised.value.status is Status.RESOURCE_EXHAUSTED


async def test_a_response_over_the_callers_limit_is_resource_exhausted(protocol, impl, export, refer):
    exporter = await export(protocol, impl, "?triple.max-receive-message-size=8")
    echo = await refer(protocol, exporter, "?triple.max-receive-message-size=4")

    with pytest.raises(RpcError, match="larger than 4") as raised:
        await echo.say(StringValue(value="hi"))

    assert raised.value.status is Status.RESOURCE_EXHAUSTED


@pytest.mark.parametrize(
    ("text", "status", "message"),
    [("rpc", Status.ABORTED, "失败 100%"), ("crash", Status.UNKNOWN, "ValueError: broken")],
    ids=["rpc-error", "handler-exception"],
)
async def test_handler_errors_reach_the_caller_with_status_and_message(echo, text, status, message):
    with pytest.raises(RpcError, match=message) as raised:
        await echo.say(StringValue(value=text))

    assert (raised.value.status, raised.value.message) == (status, message)


async def test_handler_error_details_reach_the_caller(echo):
    with pytest.raises(TripleError, match="bad request") as raised:
        await echo.say(StringValue(value="details"))

    assert (raised.value.status, raised.value.message) == (Status.INVALID_ARGUMENT, "bad request")
    assert [detail.unpack(StringValue) for detail in raised.value.details] == [StringValue(value="value")]


_COMPRESSIONS = pytest.mark.parametrize("compression", ["", "?triple.compressor=gzip"], ids=["plain", "gzip"])


async def test_a_unary_call_round_trips_compressed(protocol, impl, export, refer):
    gzip = "?triple.compressor=gzip"
    echo = await refer(protocol, await export(protocol, impl, gzip), gzip)

    assert await echo.say(StringValue(value="hi")) == StringValue(value="hi|-")


@_COMPRESSIONS
async def test_a_server_stream_round_trips(compression, protocol, impl, export, refer):
    echo = await refer(protocol, await export(protocol, impl, compression), compression)

    async with echo.count(StringValue(value="3")) as events:
        assert [event.value async for event in events] == ["0", "1", "2"]


@_COMPRESSIONS
async def test_a_client_stream_round_trips(compression, protocol, impl, export, refer):
    echo = await refer(protocol, await export(protocol, impl, compression), compression)

    async with echo.join() as upload:
        for chunk in "abc":
            await upload.send(StringValue(value=chunk))
        await upload.end()
        assert await upload.receive() == StringValue(value="a,b,c")


@_COMPRESSIONS
async def test_a_bidi_stream_round_trips(compression, protocol, impl, export, refer):
    echo = await refer(protocol, await export(protocol, impl, compression), compression)

    async with echo.chat() as chat:
        await chat.send(StringValue(value="q"))
        assert await chat.receive() == StringValue(value="Q")
        await chat.end()
        assert [answer async for answer in chat] == []


async def test_a_stream_ends_with_the_handler_error_after_its_messages(echo) -> None:
    received: list[str] = []

    async def collect() -> None:
        async with echo.count(StringValue(value="2")) as events:
            while True:
                received.append((await events.receive()).value)

    with dubbo.outgoing() as call, pytest.raises(RpcError, match="DATA_LOSS: stopped after 2"):
        await collect()

    assert received == ["0", "1"]
    assert dict(call.response_attachments) == {"counted": "2"}


async def test_a_stream_without_messages_ends_at_once(echo) -> None:
    async with echo.count(StringValue(value="0")) as events:
        assert [event async for event in events] == []


async def test_the_deadline_reaches_the_server(echo, impl) -> None:
    with pytest.raises(TimeoutError), anyio.fail_after(0.2):
        await echo.say(StringValue(value="sleep"))

    with anyio.fail_after(5):
        await impl.cancelled.wait()


async def test_a_call_that_its_provider_ends_at_its_deadline_ends_at_the_deadline_of_its_caller(
    protocol: TripleProtocol, impl, export, refer
) -> None:
    exporter = await export(protocol, impl)
    bounded = await refer(protocol, exporter, "?timeout=5000")
    timed = await refer(protocol, exporter, "?timeout=5000&Say.timeout=300")

    with pytest.raises(TimeoutError), anyio.fail_after(0.3):
        await bounded.say(StringValue(value="early"))
    with anyio.fail_after(5), pytest.raises(RpcError, match=r"Say did not complete within 0\.3 seconds"):
        await timed.say(StringValue(value="early"))


async def test_a_deadline_that_its_provider_reached_long_before_the_caller_ends_the_call_at_once(echo) -> None:
    start = anyio.current_time()

    with anyio.fail_after(5), pytest.raises(RpcError, match="the inventory did not answer in time"):
        await echo.say(StringValue(value="expired"))

    assert anyio.current_time() == start


async def test_a_stream_takes_the_deadline_of_its_caller(echo, impl) -> None:
    with anyio.fail_after(5):
        async with echo.chat() as chat:
            await chat.send(StringValue(value="q"))
            assert await chat.receive() == StringValue(value="Q")
            await chat.end()

    assert math.isfinite(impl.deadline)


async def test_a_unary_call_ends_after_the_timeout_of_its_method(protocol: TripleProtocol, impl, export, refer) -> None:
    echo = await refer(protocol, await export(protocol, impl), "?timeout=5000&Say.timeout=50")

    with anyio.fail_after(5), pytest.raises(RpcError) as raised:
        await echo.say(StringValue(value="sleep"))

    assert raised.value.status is Status.DEADLINE_EXCEEDED
    with anyio.fail_after(5):
        await impl.cancelled.wait()


# Windows refuses the connection after its own retries, in real time.
@pytest.mark.real_clock
async def test_an_invoker_is_unavailable_after_it_fails_to_connect(protocol: TripleProtocol, echo_contract) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Windows takes about two seconds to refuse a connection, longer than the default timeout.
    invoker = await protocol.refer(
        URL.parse(f"tri://127.0.0.1:{port}/test.Echo?timeout=5000"), dubbo.get_definition(echo_contract)
    )

    with pytest.raises(RpcError, match="UNAVAILABLE"):
        await proxy(echo_contract, invoker.invoke).say(StringValue(value="x"))

    assert not invoker.available


@pytest.fixture
async def grpc_peer():
    seen: dict[str, object] = {}

    async def say(request: StringValue, context: grpc.aio.ServicerContext) -> StringValue:
        seen["metadata"] = dict(context.invocation_metadata() or ())
        seen["time_remaining"] = context.time_remaining()
        if request.value == "rpc":
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "失败 100%")
        if request.value == "details":
            status = StatusMessage(code=Status.INVALID_ARGUMENT, message="bad request")
            status.details.add().Pack(StringValue(value="value"))
            context.set_trailing_metadata((("grpc-status-details-bin", status.SerializeToString()),))
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "bad request")
        context.set_trailing_metadata((("served-by", "grpcio"),))
        return StringValue(value=request.value.upper())

    async def count(request: StringValue, context: grpc.aio.ServicerContext) -> AsyncIterator[StringValue]:
        for i in range(int(request.value)):
            yield StringValue(value=str(i))

    async def join(requests: AsyncIterator[StringValue], context: grpc.aio.ServicerContext) -> StringValue:
        return StringValue(value=",".join([request.value async for request in requests]))

    async def chat(
        requests: AsyncIterator[StringValue], context: grpc.aio.ServicerContext
    ) -> AsyncIterator[StringValue]:
        async for request in requests:
            yield StringValue(value=request.value.upper())

    options = {"request_deserializer": StringValue.FromString, "response_serializer": StringValue.SerializeToString}
    handlers = {
        "Say": grpc.unary_unary_rpc_method_handler(say, **options),
        "Count": grpc.unary_stream_rpc_method_handler(count, **options),
        "Join": grpc.stream_unary_rpc_method_handler(join, **options),
        "Chat": grpc.stream_stream_rpc_method_handler(chat, **options),
    }
    server = grpc.aio.server(compression=grpc.Compression.Gzip)
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("test.Echo", handlers),))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    try:
        yield port, seen
    finally:
        await server.stop(None)


async def _grpc_echo(protocol: TripleProtocol, port: int, echo_contract, query: str = ""):
    url = URL.parse(f"tri://127.0.0.1:{port}/test.Echo{query}")
    return proxy(echo_contract, (await protocol.refer(url, dubbo.get_definition(echo_contract))).invoke)


@_grpcio
async def test_a_triple_unary_call_to_grpcio_carries_attachments_group_and_deadline(protocol, echo_contract, grpc_peer):
    port, seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract, "?group=g")

    with dubbo.outgoing({"Tenant": "t1"}) as call, anyio.fail_after(5):
        assert await echo.say(StringValue(value="hi")) == StringValue(value="HI")

    assert dict(call.response_attachments) == {"served-by": "grpcio"}
    assert (seen["metadata"]["tenant"], seen["metadata"]["tri-service-group"]) == ("t1", "g")
    assert 0 < seen["time_remaining"] <= 5


@_grpcio
async def test_triple_calls_a_grpcio_server_stream(protocol, echo_contract, grpc_peer):
    port, _seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract)

    async with echo.count(StringValue(value="3")) as events:
        assert [event.value async for event in events] == ["0", "1", "2"]


@_grpcio
async def test_triple_calls_a_grpcio_client_stream(protocol, echo_contract, grpc_peer):
    port, _seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract)

    async with echo.join() as upload:
        await upload.send(StringValue(value="a"))
        await upload.send(StringValue(value="b"))
        await upload.end()
        assert await upload.receive() == StringValue(value="a,b")


@_grpcio
async def test_triple_calls_a_grpcio_bidi_stream(protocol, echo_contract, grpc_peer):
    port, _seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract)

    async with echo.chat() as chat:
        await chat.send(StringValue(value="x"))
        assert await chat.receive() == StringValue(value="X")
        await chat.end()
        assert [answer async for answer in chat] == []


@_grpcio
async def test_triple_preserves_a_grpcio_error_status_and_message(protocol, echo_contract, grpc_peer):
    port, _seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract)

    with pytest.raises(RpcError, match="失败 100%") as raised:
        await echo.say(StringValue(value="rpc"))

    assert (raised.value.status, raised.value.message) == (Status.PERMISSION_DENIED, "失败 100%")


@_grpcio
async def test_triple_preserves_grpcio_error_details(protocol, echo_contract, grpc_peer):
    port, _seen = grpc_peer
    echo = await _grpc_echo(protocol, port, echo_contract)

    with pytest.raises(TripleError, match="bad request") as raised:
        await echo.say(StringValue(value="details"))

    assert (raised.value.status, raised.value.message) == (Status.INVALID_ARGUMENT, "bad request")
    assert [detail.unpack(StringValue) for detail in raised.value.details] == [StringValue(value="value")]


async def test_closing_an_invoker_waits_for_its_running_calls(
    protocol: TripleProtocol, impl, export, echo_contract
) -> None:
    exporter = await export(protocol, impl)
    invoker = await protocol.refer(
        URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo"), dubbo.get_definition(echo_contract)
    )
    echo = proxy(echo_contract, invoker.invoke)
    results = []

    async def call() -> None:
        results.append(await echo.say(StringValue(value="wait")))

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(call)
        await impl.started.wait()
        tasks.start_soon(invoker.aclose)
        await anyio.wait_all_tasks_blocked()

        with pytest.raises(RpcError, match="UNAVAILABLE"):
            await echo.say(StringValue(value="late"))
        impl.release.set()

    assert results == [StringValue(value="wait|-")]
    assert protocol._clients._shares == {}
