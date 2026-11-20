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
import enum
import typing
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import anyio
import attrs
import hessian2
import pytest

import dubbo
from dubbo import RemoteError, RpcError, Status
from dubbo.protocol import Protocol
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.protocol.triple import TripleProtocol
from dubbo.rpc.client import GenericService, proxy
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invocation
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio

_INTERFACE = "com.example.UserService"


@hessian2.java_class("com.example.Color")
class Color(enum.Enum):
    RED = "r"


@hessian2.java_class("com.example.Address")
@attrs.define(kw_only=True)
class Address:
    city: str


@hessian2.java_class("com.example.User")
@attrs.define(kw_only=True)
class User:
    name: str
    user_id: hessian2.Long
    address: Address | None
    color: Color | None
    tags: tuple[str, ...]


@hessian2.java_class("java.lang.IllegalStateException")
@attrs.define(kw_only=True)
class IllegalState(Exception):
    detail_message: str = ""


@dubbo.service(_INTERFACE)
class UserService(abc.ABC):
    @dubbo.method("find")
    @abc.abstractmethod
    async def find(self, name: str, user_id: hessian2.Long) -> User | None: ...

    @dubbo.method("save")
    @abc.abstractmethod
    async def save(self, user: User) -> str: ...

    @dubbo.method("fail")
    @abc.abstractmethod
    async def fail(self, how: str) -> str: ...


class UserServiceImpl(UserService):
    async def find(self, name: str, user_id: int) -> User | None:
        if name == "nobody":
            return None

        return User(name=name, user_id=user_id, address=Address(city="Hangzhou"), color=Color.RED, tags=("a",))

    async def save(self, user: User) -> str:
        return f"{user.name} {user.user_id} {user.address} {user.color} {user.tags}"

    async def fail(self, how: str) -> str:
        if how == "rpc":
            raise RpcError(Status.NOT_FOUND, "no such user")

        raise IllegalState(detail_message="not now")


def _user(name: str) -> dict[str, Any]:
    return {
        "class": "com.example.User",
        "name": name,
        "userId": 7,
        "address": {"class": "com.example.Address", "city": "Hangzhou"},
        "color": "RED",
        "tags": ["a"],
    }


@asynccontextmanager
async def _serve(name: str) -> AsyncIterator[tuple[Protocol, URL, AsyncExitStack]]:
    protocol: Protocol = DubboProtocol() if name == "dubbo" else TripleProtocol()

    with anyio.fail_after(3):
        async with protocol, AsyncExitStack() as resources:
            url = URL.parse(f"{name}://127.0.0.1:0/{_INTERFACE}?serialization=hessian2")
            invoker = ServiceInvoker.from_implementation(UserServiceImpl(), url)
            exporter = await protocol.export(url, dubbo.get_definition(UserService), invoker)
            yield protocol, exporter.url, resources


@pytest.fixture(params=["dubbo", "tri"])
async def provider(request: pytest.FixtureRequest):
    async with _serve(request.param) as served:
        yield served


async def _generic(provider, generic: str = "true") -> GenericService:
    protocol, url, resources = provider
    invoker = await protocol.refer(url, Service(interface=_INTERFACE, methods=()))
    resources.push_async_callback(invoker.aclose)

    return GenericService(_INTERFACE, invoker.invoke, generic=generic)


async def test_generic_calls_realize_class_maps_and_generalize_returned_objects(provider):
    users = await _generic(provider)

    saved = await users.call("save", _user("bob"))
    found = await users.call("find", "bob", 7, types=["java.lang.String", "long"])
    missing = await users.call("find", "nobody", 7)

    assert (saved, found, missing) == ("bob 7 Address(city='Hangzhou') Color.RED ('a',)", _user("bob"), None)


async def test_generic_calls_preserve_the_java_exception_class_and_message(provider):
    users = await _generic(provider)

    with pytest.raises(RemoteError, match="not now") as thrown:
        await users.call("fail", "declared")

    assert (thrown.value.class_name, thrown.value.message) == ("java.lang.IllegalStateException", "not now")


@pytest.mark.parametrize(
    ("provider", "status"),
    [("dubbo", Status.UNKNOWN), ("tri", Status.NOT_FOUND)],
    ids=["dubbo", "tri"],
    indirect=["provider"],
)
async def test_generic_calls_report_the_provider_failure_in_the_protocols_error_form(provider, status):
    users = await _generic(provider)

    with pytest.raises(RpcError, match="no such user") as raised:
        await users.call("fail", "rpc")

    assert (raised.value.status, raised.value.message) == (status, "no such user")


@pytest.mark.parametrize(
    ("provider", "generic", "method", "arguments", "message", "status"),
    [
        ("dubbo", "gson", "find", ('"bob"', "7"), "the mode 'gson' are not served", Status.UNIMPLEMENTED),
        ("dubbo", "true", "missing", (), "has no unary method 'missing'", Status.UNIMPLEMENTED),
        ("dubbo", "true", "save", ("bob", 7), "the arguments of save", Status.UNKNOWN),
        ("dubbo", "true", "save", ("bob",), "the arguments of save", Status.UNKNOWN),
        ("tri", "gson", "find", ('"bob"', "7"), "the mode 'gson' are not served", Status.UNIMPLEMENTED),
        ("tri", "true", "missing", (), "has no unary method 'missing'", Status.UNIMPLEMENTED),
        ("tri", "true", "save", ("bob", 7), "the arguments of save", Status.INVALID_ARGUMENT),
        ("tri", "true", "save", ("bob",), "the arguments of save", Status.INVALID_ARGUMENT),
    ],
    ids=[
        f"{protocol}-{case}"
        for protocol in ("dubbo", "tri")
        for case in ("unsupported-mode", "unknown-method", "wrong-arity", "wrong-type")
    ],
    indirect=["provider"],
)
async def test_generic_calls_fail_when_the_provider_cannot_serve_them(
    provider, generic, method, arguments, message, status
):
    users = await _generic(provider, generic)

    with pytest.raises(RpcError, match=message) as raised:
        await users.call(method, *arguments)

    assert raised.value.status is status


async def test_triple_preserves_a_declared_java_exception_separately_from_a_status():
    async with _serve("tri") as (protocol, url, resources):
        invoker = await protocol.refer(url, dubbo.get_definition(UserService))
        resources.push_async_callback(invoker.aclose)
        users = proxy(UserService, invoker.invoke)

        with pytest.raises(RemoteError, match="not now") as thrown:
            await users.fail("declared")
        with pytest.raises(RpcError, match="no such user") as status:
            await users.fail("rpc")

    assert (thrown.value.class_name, thrown.value.message) == ("java.lang.IllegalStateException", "not now")
    assert not isinstance(status.value, RemoteError)
    assert status.value.status is Status.NOT_FOUND


async def test_echo_returns_the_argument_without_calling_a_service_method(provider):
    protocol, url, resources = provider
    echo = dubbo.Method(name="$echo", request=(dubbo.Parameter(name="value", type=Any),), response=Any)
    invoker = await protocol.refer(url, Service(interface=_INTERFACE, methods=(echo,)))
    resources.push_async_callback(invoker.aclose)
    call = Invocation(interface=_INTERFACE, method="$echo", definition=echo, arguments=({"k": [1]},))

    result = await invoker.invoke(call)

    assert (result.value, result.error) == ({"k": [1]}, None)


@dubbo.service("test.RpcStreams")
class Streams(typing.Protocol):
    def watch(self, query: str) -> dubbo.ServerStream[int]: ...
    def upload(self) -> dubbo.ClientStream[bytes, int]: ...
    def chat(self) -> dubbo.BidiStream[str, str]: ...


@dubbo.service("test.RpcStreams")
class StreamService:
    def __init__(self) -> None:
        self.started = anyio.Event()
        self.cancelled = anyio.Event()

    async def watch(self, query: str, events: dubbo.SendStream[int]) -> None:
        self.started.set()
        try:
            await events.send(0)
            await anyio.sleep_forever()
        finally:
            self.cancelled.set()

    async def upload(self, chunks: dubbo.ReceiveStream[bytes]) -> int:
        total = sum([len(chunk) async for chunk in chunks])
        if not total:
            raise RpcError(Status.INVALID_ARGUMENT, "nothing uploaded")

        return total

    async def chat(self, stream: dubbo.Stream[str, str]) -> None:
        async for question in stream:
            if question == "fail":
                raise RpcError(Status.ABORTED, "asked to fail")

            await stream.send(question.upper())


@pytest.fixture
async def stream_provider():
    implementation = StreamService()

    with anyio.fail_after(3):
        async with TripleProtocol() as protocol, AsyncExitStack() as resources:
            url = URL.parse("tri://127.0.0.1:0/test.RpcStreams?serialization=hessian2")
            exporter = await protocol.export(
                url, dubbo.get_definition(Streams), ServiceInvoker.from_implementation(implementation, url)
            )
            yield protocol, exporter.url, resources, implementation


@pytest.fixture
async def streams(stream_provider):
    protocol, url, resources, _ = stream_provider
    invoker = await protocol.refer(url, dubbo.get_definition(Streams))
    resources.push_async_callback(invoker.aclose)

    return proxy(Streams, invoker.invoke)


async def test_client_stream_receive_raises_the_handler_error(streams):
    async with streams.upload() as stream:
        await stream.end()

        with pytest.raises(RpcError, match="INVALID_ARGUMENT: nothing uploaded"):
            await stream.receive()


async def test_bidi_stream_receive_raises_the_handler_error(streams):
    async with streams.chat() as stream:
        await stream.send("fail")

        with pytest.raises(RpcError, match="ABORTED: asked to fail"):
            await stream.receive()


async def test_bidi_stream_receive_ends_when_the_handler_returns(streams):
    async with streams.chat() as stream:
        await stream.end()

        with pytest.raises(dubbo.EndOfStream):
            await stream.receive()


async def test_bidi_stream_send_repeats_the_handler_error_already_received(streams):
    async with streams.chat() as stream:
        await stream.send("fail")
        with pytest.raises(RpcError, match="ABORTED: asked to fail"):
            await stream.receive()

        with pytest.raises(RpcError, match="ABORTED: asked to fail"):
            await stream.send("more")


async def test_a_stream_deadline_cancels_the_provider_handler(streams, stream_provider):
    implementation = stream_provider[3]

    async def watch() -> None:
        with anyio.fail_after(None) as deadline:
            async with streams.watch("wait") as events:
                assert await events.receive() == 0
                deadline.deadline = anyio.current_time()
                await events.receive()

    with pytest.raises(TimeoutError):
        await watch()
    with anyio.fail_after(5):
        await implementation.cancelled.wait()

    assert implementation.started.is_set()


async def test_generic_calls_cannot_invoke_a_streaming_method(stream_provider):
    protocol, url, resources, implementation = stream_provider
    invoker = await protocol.refer(url, Service(interface="test.RpcStreams", methods=()))
    resources.push_async_callback(invoker.aclose)
    generic = GenericService("test.RpcStreams", invoker.invoke)

    with pytest.raises(RpcError, match="has no unary method 'watch'") as raised:
        await generic.call("watch", "wait")

    assert raised.value.status is Status.UNIMPLEMENTED
    assert not implementation.started.is_set()
