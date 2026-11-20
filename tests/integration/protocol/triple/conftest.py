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

import abc
import math
import typing
from collections.abc import AsyncIterator

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo.protocol import Exporter
from dubbo.protocol.triple import ErrorDetail, TripleError, TripleProtocol
from dubbo.rpc.client import proxy
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL


@dubbo.service("test.Echo")
class Echo(typing.Protocol):
    @dubbo.method("Say")
    async def say(self, request: StringValue) -> StringValue: ...

    @dubbo.method("Count")
    def count(self, request: StringValue) -> dubbo.ServerStream[StringValue]: ...

    @dubbo.method("Join")
    def join(self) -> dubbo.ClientStream[StringValue, StringValue]: ...

    @dubbo.method("Chat")
    def chat(self) -> dubbo.BidiStream[StringValue, StringValue]: ...


@dubbo.service("test.Echo")
class EchoServicer(abc.ABC):
    @dubbo.method("Say")
    @abc.abstractmethod
    async def say(self, request: StringValue) -> StringValue: ...

    @dubbo.method("Count")
    @abc.abstractmethod
    async def count(self, request: StringValue, stream: dubbo.SendStream[StringValue]) -> None: ...

    @dubbo.method("Join")
    @abc.abstractmethod
    async def join(self, stream: dubbo.ReceiveStream[StringValue]) -> StringValue: ...

    @dubbo.method("Chat")
    @abc.abstractmethod
    async def chat(self, stream: dubbo.Stream[StringValue, StringValue]) -> None: ...


class EchoImpl(EchoServicer):
    def __init__(self) -> None:
        self.cancelled = anyio.Event()
        self.release = anyio.Event()
        self.started = anyio.Event()
        self.peer: str | None = None
        self.deadline = math.inf

    async def say(self, request: StringValue) -> StringValue:
        call = dubbo.incoming()
        self.peer = call.peer
        call.response_attachments["Served-By"] = "echo"
        for key in ("trace-bin", "tag", "token"):
            call.response_attachments.extend((key, value) for value in call.attachments.getall(key, []))
        match request.value:
            case "rpc":
                raise RpcError(Status.ABORTED, "失败 100%")
            case "details":
                raise TripleError(
                    Status.INVALID_ARGUMENT,
                    "bad request",
                    details=[ErrorDetail.from_message(StringValue(value="value"))],
                )
            case "crash":
                raise ValueError("broken")
            case "sleep":
                try:
                    self.started.set()
                    await anyio.sleep_forever()
                finally:
                    self.cancelled.set()
            case "wait":
                self.started.set()
                await self.release.wait()
            case "early":
                # As a provider whose clock reaches the deadline of the call a moment before the caller's.
                await anyio.sleep_until(anyio.current_effective_deadline() - 0.02)
                raise RpcError(Status.DEADLINE_EXCEEDED, "the call ran out of time")
            case "expired":
                # As a provider whose own call to another service ran out of time.
                raise RpcError(Status.DEADLINE_EXCEEDED, "the inventory did not answer in time")
        return StringValue(value=f"{request.value}|{call.attachments.get('Tenant', '-')}")

    async def count(self, request: StringValue, stream: dubbo.SendStream[StringValue]) -> None:
        dubbo.incoming().response_attachments["counted"] = request.value
        for i in range(int(request.value)):
            await stream.send(StringValue(value=str(i)))
        if request.value == "2":
            raise RpcError(Status.DATA_LOSS, "stopped after 2")

    async def join(self, stream: dubbo.ReceiveStream[StringValue]) -> StringValue:
        return StringValue(value=",".join([chunk.value async for chunk in stream]))

    async def chat(self, stream: dubbo.Stream[StringValue, StringValue]) -> None:
        self.deadline = anyio.current_effective_deadline()
        async for question in stream:
            await stream.send(StringValue(value=question.value.upper()))


@pytest.fixture
async def protocol() -> AsyncIterator[TripleProtocol]:
    async with TripleProtocol() as protocol:
        yield protocol


@pytest.fixture
def impl() -> EchoImpl:
    return EchoImpl()


async def _export(protocol: TripleProtocol, impl: object, query: str = "") -> Exporter:
    return await _serve(protocol, URL.parse(f"tri://127.0.0.1:0/test.Echo{query}"), impl)


async def _serve(protocol: TripleProtocol, url: URL, impl: object, contract: type = Echo) -> Exporter:
    return await protocol.export(url, dubbo.get_definition(contract), ServiceInvoker.from_implementation(impl, url))


async def _refer(protocol: TripleProtocol, exporter: Exporter, query: str = "") -> Echo:
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo{query}")
    return proxy(Echo, (await protocol.refer(url, dubbo.get_definition(Echo))).invoke)


@pytest.fixture
async def echo(protocol: TripleProtocol, impl: EchoImpl) -> Echo:
    return await _refer(protocol, await _export(protocol, impl))


@pytest.fixture
def export():
    return _export


@pytest.fixture
def serve():
    return _serve


@pytest.fixture
def refer():
    return _refer


@pytest.fixture
def echo_contract():
    return Echo


@pytest.fixture
def echo_impl_type():
    return EchoImpl
