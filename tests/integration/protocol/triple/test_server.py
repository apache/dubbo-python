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
import grpc
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo._proto.google.rpc.status_pb2 import Status as StatusMessage
from dubbo.protocol import Exporter
from dubbo.protocol.triple import TripleProtocol
from dubbo.rpc import Invocation
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio

# grpcio calls through threads of its own and keeps its deadlines on the real clock.
_grpcio = pytest.mark.real_clock


class _Broken(ServiceInvoker):
    async def invoke(self, invocation: Invocation):
        raise RuntimeError("broken")


async def test_an_invoker_that_raises_answers_internal(protocol: TripleProtocol, impl, refer, echo_contract) -> None:
    url = URL.parse("tri://127.0.0.1:0/test.Echo")
    exporter = await protocol.export(url, dubbo.get_definition(echo_contract), _Broken.from_implementation(impl, url))
    echo = await refer(protocol, exporter)

    with pytest.raises(RpcError, match=r"^INTERNAL: RuntimeError: broken$") as caught:
        await echo.say(StringValue(value="hi"))

    assert caught.value.status is Status.INTERNAL


async def test_a_handler_sees_the_caller_address(echo, impl) -> None:
    await echo.say(StringValue(value="hi"))

    assert impl.peer is not None
    host, _, port = impl.peer.rpartition(":")
    assert host == "127.0.0.1"
    assert int(port) > 0


async def test_a_handler_is_cancelled_when_the_caller_leaves(
    protocol: TripleProtocol, export, refer, echo_impl_type
) -> None:
    seen: list[BaseException] = []
    finished = anyio.Event()

    class Impl(echo_impl_type):
        async def chat(self, stream: dubbo.Stream[StringValue, StringValue]) -> None:
            await stream.send(await stream.receive())
            try:
                await stream.receive()
            except BaseException as error:
                seen.append(error)
                raise
            finally:
                finished.set()

    echo = await refer(protocol, await export(protocol, Impl()))
    async with echo.chat() as chat:
        await chat.send(StringValue(value="x"))
        assert await chat.receive() == StringValue(value="x")

    with anyio.fail_after(5):
        await finished.wait()
    assert isinstance(seen[0], anyio.get_cancelled_exc_class())


_MESSAGES = {"request_serializer": StringValue.SerializeToString, "response_deserializer": StringValue.FromString}


def _channel(exporter: Exporter) -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(f"127.0.0.1:{exporter.url.port}")


async def _grpcio_error(
    exporter: Exporter, method: str, text: str, timeout: float | None = None
) -> grpc.aio.AioRpcError:
    async with _channel(exporter) as channel:
        call = channel.unary_unary(f"/test.Echo/{method}", request_serializer=StringValue.SerializeToString)
        with pytest.raises(grpc.aio.AioRpcError) as raised:
            await call(StringValue(value=text), timeout=timeout)

    return raised.value


@_grpcio
async def test_a_grpcio_unary_call_carries_metadata_both_ways_compressed(protocol, impl, export):
    exporter = await export(protocol, impl)
    metadata = (
        ("tenant", "t1"),
        ("tri-header-convert", '{"tenant":"Tenant"}'),
        ("trace-bin", b"\x00\xff"),
        ("tag", "a"),
        ("tag", "b"),
    )

    async with _channel(exporter) as channel:
        say = channel.unary_unary("/test.Echo/Say", **_MESSAGES)
        call = say(StringValue(value="hi"), metadata=metadata, compression=grpc.Compression.Gzip)
        assert await call == StringValue(value="hi|t1")
        trailers = tuple(await call.trailing_metadata())

    assert ("served-by", "echo") in trailers
    assert ("trace-bin", b"\x00\xff") in trailers
    assert [value for key, value in trailers if key == "tag"] == ["a", "b"]


@_grpcio
async def test_a_grpcio_client_calls_a_triple_server_stream(protocol, impl, export):
    exporter = await export(protocol, impl)

    async with _channel(exporter) as channel:
        count = channel.unary_stream("/test.Echo/Count", **_MESSAGES)
        assert [event.value async for event in count(StringValue(value="3"))] == ["0", "1", "2"]


@_grpcio
async def test_a_grpcio_client_calls_a_triple_client_stream(protocol, impl, export):
    exporter = await export(protocol, impl)

    async with _channel(exporter) as channel:
        join = channel.stream_unary("/test.Echo/Join", **_MESSAGES)
        assert await join(iter([StringValue(value="a"), StringValue(value="b")])) == StringValue(value="a,b")


@_grpcio
async def test_a_grpcio_client_calls_a_triple_bidi_stream(protocol, impl, export):
    exporter = await export(protocol, impl)

    async with _channel(exporter) as channel:
        chat = channel.stream_stream("/test.Echo/Chat", **_MESSAGES)
        answers = [answer.value async for answer in chat(iter([StringValue(value="x"), StringValue(value="y")]))]

    assert answers == ["X", "Y"]


@_grpcio
async def test_a_grpcio_client_receives_a_triple_rpc_error_with_its_message(protocol, impl, export):
    error = await _grpcio_error(await export(protocol, impl), "Say", "rpc")

    assert (error.code(), error.details()) == (grpc.StatusCode.ABORTED, "失败 100%")


@_grpcio
async def test_a_grpcio_client_receives_triple_error_details(protocol, impl, export):
    error = await _grpcio_error(await export(protocol, impl), "Say", "details")

    assert error.code() is grpc.StatusCode.INVALID_ARGUMENT
    details = StatusMessage.FromString(dict(error.trailing_metadata())["grpc-status-details-bin"])
    assert (details.code, details.message) == (Status.INVALID_ARGUMENT, "bad request")
    assert [detail.value for detail in details.details] == [StringValue(value="value").SerializeToString()]


@_grpcio
async def test_a_grpcio_client_calling_an_unknown_method_receives_unimplemented(protocol, impl, export):
    error = await _grpcio_error(await export(protocol, impl), "Nope", "x")

    assert error.code() is grpc.StatusCode.UNIMPLEMENTED


@_grpcio
async def test_a_triple_handler_whose_caller_gives_up_finishes_its_shielded_work_first(protocol, impl, export):
    committed = anyio.Event()

    class Committing(type(impl)):
        async def say(self, request: StringValue) -> StringValue:
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0.2)
                committed.set()
            await anyio.sleep_forever()
            return request

    error = await _grpcio_error(await export(protocol, Committing()), "Say", "commit", timeout=0.05)

    assert error.code() is grpc.StatusCode.DEADLINE_EXCEEDED
    with anyio.fail_after(2):
        await committed.wait()


@_grpcio
async def test_a_grpcio_deadline_ends_and_cancels_the_triple_handler(protocol, impl, export):
    error = await _grpcio_error(await export(protocol, impl), "Say", "sleep", timeout=0.2)

    assert error.code() is grpc.StatusCode.DEADLINE_EXCEEDED
    await impl.cancelled.wait()
