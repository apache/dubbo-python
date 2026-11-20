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
import typing
from collections.abc import AsyncIterator
from typing import Any

import pytest
from google.protobuf.wrappers_pb2 import StringValue
from hessian2 import HessianObject

import dubbo
from dubbo._proto.org.apache.dubbo.triple.triple_wrapper_pb2 import TripleResponseWrapper
from dubbo.exceptions import RemoteError
from dubbo.protocol.triple import TripleProtocol
from dubbo.protocol.triple.grpc.framing import frame
from dubbo.rpc.client import GenericService, proxy
from dubbo.rpc.definition import Service
from dubbo.rpc.server import ServiceInvoker
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.transport.h2 import H2Stream
from dubbo.transport.h2.aio import AioH2Server
from dubbo.url import URL

pytestmark = pytest.mark.anyio


@pytest.fixture
def hessian2() -> Hessian2Serialization:
    return Hessian2Serialization(URL(protocol="tri"))


@dubbo.service("test.Users")
class Users(typing.Protocol):
    @dubbo.method("greet")
    async def greet(self, name: str, times: int) -> str: ...


@dubbo.service("test.Users")
class UsersServicer(abc.ABC):
    @dubbo.method("greet")
    @abc.abstractmethod
    async def greet(self, name: str, times: int) -> str: ...

    @dubbo.method("$invoke")
    @abc.abstractmethod
    async def echo_generic_call(
        self, method: str, types: tuple[str, ...] | None, arguments: tuple[Any, ...]
    ) -> Any: ...


class UsersImpl(UsersServicer):
    async def greet(self, name: str, times: int) -> str:
        return " ".join([f"hi {name}"] * times)

    async def echo_generic_call(self, method: str, types: tuple[str, ...] | None, arguments: tuple[Any, ...]) -> Any:
        return {"method": method, "types": types, "arguments": arguments, **dubbo.incoming().attachments}


@pytest.fixture
async def port() -> AsyncIterator[tuple[TripleProtocol, int]]:
    async with TripleProtocol() as protocol:
        url = URL.parse("tri://127.0.0.1:0/test.Users?serialization=hessian2")
        invoker = ServiceInvoker.from_implementation(UsersImpl(), url)
        exporter = await protocol.export(url, dubbo.get_definition(UsersServicer), invoker)
        yield protocol, exporter.url.port or 0


async def test_a_java_format_travels_wrapped_with_all_its_parameters(port: tuple[TripleProtocol, int]) -> None:
    protocol, number = port
    url = URL.parse(f"tri://127.0.0.1:{number}/test.Users?serialization=hessian2")

    users = proxy(Users, (await protocol.refer(url, dubbo.get_definition(Users))).invoke)

    assert await users.greet("bob", 2) == "hi bob hi bob"


async def test_a_generic_call_travels_as_wrapped_invoke_whatever_the_format(port: tuple[TripleProtocol, int]) -> None:
    protocol, number = port
    url = URL.parse(f"tri://127.0.0.1:{number}/test.Users?serialization=protobuf")
    invoker = await protocol.refer(url, Service(interface="test.Users", methods=()))
    users = GenericService("test.Users", invoker.invoke)

    received = await users.call("find", "bob", 7)
    typed = await users.call("find", "bob", 7, types=["java.lang.String", "long"])

    assert received["method"] == "find"
    assert received["types"] is None
    assert received["arguments"] == ["bob", 7]
    assert received["generic"] == "true"
    assert typed["types"] == ["java.lang.String", "long"]


async def test_a_response_flagged_as_an_exception_is_the_error_of_the_call(hessian2: Hessian2Serialization) -> None:
    thrown = HessianObject("java.lang.IllegalStateException", {"detailMessage": "broken"})
    message = TripleResponseWrapper(
        serializeType="hessian4", data=hessian2.codec((Any,)).encode((thrown,))
    ).SerializeToString()

    async def respond(stream: H2Stream) -> None:
        await stream.receive_headers()
        await stream.send_headers(
            ((b":status", b"200"), (b"content-type", b"application/grpc+proto"), (b"tri-exception-code", b"3"))
        )
        await stream.send_data(frame(message))
        await stream.send_trailers(((b"grpc-status", b"0"),))

    async with (
        TripleProtocol() as protocol,
        AioH2Server(URL(protocol="tri", host="127.0.0.1", port=0), respond) as server,
    ):
        url = URL.parse(f"tri://127.0.0.1:{server.address[1]}/test.Users?serialization=hessian2")
        users = proxy(Users, (await protocol.refer(url, dubbo.get_definition(Users))).invoke)

        with pytest.raises(RemoteError) as raised:
            await users.greet("bob", 1)

    assert raised.value.class_name == "java.lang.IllegalStateException"
    assert raised.value.message == "broken"


@dubbo.service("test.Echo")
class Echo(typing.Protocol):
    @dubbo.method("Say")
    async def say(self, request: StringValue) -> StringValue: ...


class EchoImpl(Echo):
    async def say(self, request: StringValue) -> StringValue:
        return StringValue(value=request.value.upper())


async def test_protobuf_messages_travel_as_themselves_where_the_service_names_a_java_format() -> None:
    async with TripleProtocol() as protocol:
        served = URL.parse("tri://127.0.0.1:0/test.Echo?serialization=hessian2")
        invoker = ServiceInvoker.from_implementation(EchoImpl(), served)
        exporter = await protocol.export(served, dubbo.get_definition(Echo), invoker)
        # A consumer of protobuf, as a gRPC client or a Java consumer of the proto file calls.
        called = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo")
        echo = proxy(Echo, (await protocol.refer(called, dubbo.get_definition(Echo))).invoke)

        assert (await echo.say(StringValue(value="bob"))).value == "BOB"
