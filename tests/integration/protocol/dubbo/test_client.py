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
import struct
import typing
from pathlib import Path
from typing import Any

import anyio
import hessian2
import pytest
from anyio.abc import SocketAttribute
from anyio.streams.buffered import BufferedByteReceiveStream

import dubbo
from dubbo import Method, Parameter, RemoteError, RpcError, Status
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.protocol.dubbo.connection import DubboConnection
from dubbo.rpc.client import proxy
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invocation
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio

_CERT_FILE = Path(__file__).resolve().parents[3] / "certificates" / "localhost-cert.pem"


_KEY_FILE = Path(__file__).resolve().parents[3] / "certificates" / "localhost-key.pem"


@dubbo.service("com.example.Lookup")
class ByName(typing.Protocol):
    @dubbo.method("find")
    async def find(self, key: str) -> str: ...


@dubbo.service("com.example.Lookup")
class ById(typing.Protocol):
    @dubbo.method("find")
    async def find(self, key: int) -> str: ...


async def test_a_call_returns_the_declared_classes(users, user_type, address_type) -> None:
    user = await users.find("bob", 7)

    assert user == user_type(name="bob", user_id=7, address=address_type(city="Hangzhou"))


async def test_nothing_returned_reaches_the_caller_as_none(users, impl) -> None:
    assert await users.find("nobody", 1) is None
    assert await users.forget("bob") is None
    assert impl.forgotten == ["bob"]


async def test_attachments_travel_both_ways(
    protocol: DubboProtocol, impl, export, find_invocation, user_service
) -> None:
    exporter = await export(protocol, impl)
    url = URL.parse(f"dubbo://127.0.0.1:{exporter.url.port}/com.example.UserService")
    invoker = await protocol.refer(url, dubbo.get_definition(user_service))

    invocation = find_invocation(arguments=("bob", 7))
    invocation.attachments["tag"] = "gray"
    result = await invoker.invoke(invocation)

    assert result.error is None
    assert result.attachments["served-by"] == "users"
    assert result.attachments["tag"] == "gray"
    assert result.attachments["dubbo"] == "2.0.2"


@pytest.mark.parametrize(
    ("how", "class_name", "message", "fields"),
    [
        ("rpc", "org.apache.dubbo.rpc.RpcException", "no such user", {"code": 0}),
        ("crash", "java.lang.RuntimeException", "ValueError: broken", {}),
        ("declared", "java.lang.IllegalStateException", "not now", {}),
        ("remote", "com.example.UserNotFound", "bob", {"code": 3}),
    ],
    ids=["rpc-error", "python-exception", "declared-class", "remote-error"],
)
async def test_handler_exceptions_preserve_their_java_class_message_and_fields(users, how, class_name, message, fields):
    with pytest.raises(RemoteError, match=message) as raised:
        await users.fail(how)

    assert (raised.value.status, raised.value.class_name, raised.value.message) == (Status.UNKNOWN, class_name, message)
    assert {key: raised.value.fields[key] for key in fields} == fields


async def test_a_service_of_version_0_0_0_is_one_without_a_version(
    protocol: DubboProtocol, impl, export, refer
) -> None:
    exporter = await export(protocol, impl, "?version=0.0.0")

    assert (await (await refer(protocol, exporter)).find("bob", 1)).name == "bob"


async def test_a_call_travels_over_tls(protocol: DubboProtocol, impl, export, refer) -> None:
    exporter = await export(protocol, impl, f"?ssl-enabled=true&tls-cert-file={_CERT_FILE}&tls-key-file={_KEY_FILE}")

    users = await refer(protocol, exporter, f"?ssl-enabled=true&ca-cert-file={_CERT_FILE}&tls-server-name=localhost")
    cleartext = await refer(protocol, exporter)

    assert (await users.find("bob", 1)).name == "bob"
    with pytest.raises(RpcError) as caught:
        await cleartext.find("bob", 1)
    assert caught.value.status is Status.UNAVAILABLE


async def test_a_serialization_of_no_java_objects_cannot_carry_dubbo(protocol: DubboProtocol, impl, export) -> None:
    with pytest.raises(ValueError, match="no id in the Dubbo protocol"):
        await export(protocol, impl, "?serialization=protobuf")


async def test_a_method_the_provider_lacks_is_not_found(
    protocol: DubboProtocol, impl, export, refer, wider_service
) -> None:
    wider = await refer(protocol, await export(protocol, impl), contract=wider_service)

    with pytest.raises(RpcError) as caught:
        await wider.missing()

    assert caught.value.status is Status.UNAVAILABLE
    assert (await wider.find("bob", 1)).name == "bob"


async def test_group_and_version_choose_the_service(protocol: DubboProtocol, impl, export, refer) -> None:
    exporter = await export(protocol, impl, "?group=a&version=1.0")

    assert (await (await refer(protocol, exporter, "?group=a&version=1.0")).find("bob", 1)).name == "bob"
    for query in ("", "?group=a", "?version=1.0", "?group=b&version=1.0"):
        with pytest.raises(RpcError) as caught:
            await (await refer(protocol, exporter, query)).find("bob", 1)
        assert caught.value.status is Status.UNAVAILABLE


async def test_a_call_ends_at_its_timeout(protocol: DubboProtocol, impl, export, refer) -> None:
    users = await refer(protocol, await export(protocol, impl, "?shutwait=50"), "?timeout=100")

    with pytest.raises(RpcError) as caught:
        await users.sleep()

    assert caught.value.status is Status.DEADLINE_EXCEEDED


async def test_a_call_may_not_attach_what_routes_it(users) -> None:
    with dubbo.outgoing({"group": "admin"}), pytest.raises(RpcError) as caught:
        await users.find("bob", 1)

    assert caught.value.status is Status.INVALID_ARGUMENT
    assert "group" in caught.value.message


async def test_a_call_beyond_the_most_at_once_is_refused(protocol: DubboProtocol, impl, export, refer) -> None:
    users = await refer(protocol, await export(protocol, impl, "?max-concurrent-calls=1&shutwait=50"))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(users.sleep)
        await impl.started.wait()
        with pytest.raises(RpcError) as caught:
            await users.find("bob", 1)
        task_group.cancel_scope.cancel()

    assert caught.value.status is Status.UNAVAILABLE
    assert "1 calls at once" in caught.value.message


async def test_a_generic_call_travels_as_invoke(protocol: DubboProtocol, frame) -> None:
    requests: list[list[Any]] = []

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while header := await reader.read(16):
            _, _, _, request_id, length = struct.unpack(">HBBqI", header)
            requests.append(hessian2.loads_many(await reader.readexactly(length)))
            body = hessian2.dumps_many([1, {"class": "com.example.User", "name": "bob"}])
            writer.write(frame(2, request_id, body, status=20))
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.UserService?version=1.0&getUser.timeout=2500")
        invoker = await protocol.refer(url, Service(interface="com.example.UserService", methods=()))
        users = dubbo.GenericService("com.example.UserService", invoker.invoke)

        assert await users.call("getUser", "bob", 7) == {"class": "com.example.User", "name": "bob"}
        await users.call("find", {"name": "bob"}, 7, types=["com.example.Query", "long"])
        await invoker.aclose()

    head = [
        "2.0.2",
        "com.example.UserService",
        "1.0",
        "$invoke",
        "Ljava/lang/String;[Ljava/lang/String;[Ljava/lang/Object;",
    ]
    first, second = requests
    assert first[:8] == [*head, "getUser", None, ["bob", 7]]
    assert second[:8] == [*head, "find", ["com.example.Query", "long"], [{"name": "bob"}, 7]]
    assert (first[8]["generic"], first[8]["timeout"], second[8]["timeout"]) == ("true", "2500", "1000")


async def test_echo_returns_its_argument(protocol: DubboProtocol, impl, export) -> None:
    exporter = await export(protocol, impl)
    echo = Service(
        interface="com.example.UserService",
        methods=[Method(name="$echo", request=(Parameter(name="value", type=Any),), response=Any)],
    )
    url = URL.parse(f"dubbo://127.0.0.1:{exporter.url.port}/com.example.UserService")
    invoker = await protocol.refer(url, echo)

    result = await invoker.invoke(
        Invocation(interface="com.example.UserService", method="$echo", definition=echo.methods[0], arguments=("ping",))
    )

    assert (result.value, result.error) == ("ping", None)


async def test_a_large_body_crosses_several_reads(users, user_type, address_type) -> None:
    name = "x" * (3 * 1024 * 1024)

    user = await users.find(name, 1)

    assert user == user_type(name=name, user_id=1, address=address_type(city="Hangzhou"))


async def test_a_body_over_the_payload_is_refused(protocol: DubboProtocol, impl, export, refer) -> None:
    users = await refer(protocol, await export(protocol, impl), "?payload=1000")

    with pytest.raises(RpcError) as caught:
        await users.find("x" * 2000, 1)

    assert caught.value.status is Status.RESOURCE_EXHAUSTED


async def test_a_call_in_flight_fails_when_the_provider_closes(impl, export, refer) -> None:
    async with DubboProtocol() as caller, DubboProtocol() as provider:
        exporter = await export(provider, impl, "?shutwait=50")
        users = await refer(caller, exporter)

        async with anyio.create_task_group() as task_group:

            async def call() -> None:
                with pytest.raises(RpcError) as caught:
                    await users.sleep()
                assert caught.value.status is Status.UNAVAILABLE

            task_group.start_soon(call)
            await impl.started.wait()
            await provider.aclose()


async def test_a_provider_that_takes_calls_again_is_available_again(
    protocol: DubboProtocol, find_invocation, user_service, frame
) -> None:
    readonly_in_long_string_form, writable = b"S\x00\x01R", hessian2.dumps("W")
    notices: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        _, _, _, request_id, length = struct.unpack(">HBBqI", await reader.readexactly(16))
        await reader.readexactly(length)
        body = hessian2.dumps_many([2])
        writer.write(frame(2, request_id, body, status=20))
        while (notice := await notices.get()) is not None:
            writer.write(frame(0x80 | 0x20 | 2, 0, notice))
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.UserService")
        invoker = await protocol.refer(url, dubbo.get_definition(user_service))
        await invoker.invoke(find_invocation(arguments=("bob", 1)))

        for notice, available in ((readonly_in_long_string_form, False), (writable, True)):
            notices.put_nowait(notice)
            with anyio.fail_after(5):
                while invoker.available is not available:
                    await anyio.wait_all_tasks_blocked()
        notices.put_nowait(None)


async def test_a_closing_provider_refuses_new_calls_while_running_ones_finish(impl, export, refer):
    async with DubboProtocol() as caller, DubboProtocol() as provider:
        users = await refer(caller, await export(provider, impl, "?shutwait=5000"))
        results = []

        async def call():
            results.append(await users.sleep())

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(call)
            await impl.started.wait()
            tasks.start_soon(provider.aclose)
            await anyio.wait_all_tasks_blocked()
            with pytest.raises(RpcError, match="UNAVAILABLE") as raised:
                await users.find("bob", 1)
            assert raised.value.status is Status.UNAVAILABLE
            assert results == []
            impl.released.set()

    assert results == [""]


async def test_a_caller_reconnects_after_the_peer_closes_its_socket(
    protocol, user_service, user_type, address_type, frame, monkeypatch
):
    accepted = []
    lost = anyio.Event()
    connection_lost = DubboConnection.connection_lost

    def record(connection, error):
        connection_lost(connection, error)
        lost.set()

    # The caller reconnects once it has seen the connection close, which comes after the peer closes it.
    monkeypatch.setattr(DubboConnection, "connection_lost", record)

    async def answer(stream):
        async with stream:
            reader = BufferedByteReceiveStream(stream)
            header = await reader.receive_exactly(16)
            _, _, _, request_id, length = struct.unpack(">HBBqI", header)
            await reader.receive_exactly(length)
            accepted.append(request_id)
            body = hessian2.dumps_many([1, user_type(name="bob", user_id=1, address=address_type(city="Hangzhou"))])
            await stream.send(frame(2, request_id, body, status=20))

    async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener, anyio.create_task_group() as tasks:
        tasks.start_soon(listener.serve, answer)
        port = listener.extra(SocketAttribute.local_port)
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.UserService")
        users = proxy(user_service, (await protocol.refer(url, dubbo.get_definition(user_service))).invoke)

        assert (await users.find("bob", 1)).name == "bob"
        await lost.wait()
        assert (await users.find("bob", 1)).name == "bob"
        assert len(accepted) == 2
        tasks.cancel_scope.cancel()


async def test_groups_may_export_a_method_with_other_parameters_each_its_own(protocol: DubboProtocol) -> None:
    class Named(ByName):
        async def find(self, key: str) -> str:
            return f"name {key}"

    class Numbered(ById):
        async def find(self, key: int) -> str:
            return f"id {key}"

    exporters = []
    for contract, impl, group in ((ByName, Named(), "a"), (ById, Numbered(), "b")):
        url = URL.parse(
            f"dubbo://127.0.0.1:{exporters[0].url.port if exporters else 0}/com.example.Lookup?group={group}"
        )
        exporters.append(
            await protocol.export(url, dubbo.get_definition(contract), ServiceInvoker.from_implementation(impl, url))
        )

    port = exporters[0].url.port
    for contract, group, key, expected in ((ByName, "a", "bob", "name bob"), (ById, "b", 7, "id 7")):
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.Lookup?group={group}")
        caller = proxy(contract, (await protocol.refer(url, dubbo.get_definition(contract))).invoke)
        assert await caller.find(key) == expected

    url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.Lookup?group=a")
    stale = proxy(ById, (await protocol.refer(url, dubbo.get_definition(ById))).invoke)
    with pytest.raises(RpcError, match="SERVICE_NOT_FOUND"):
        await stale.find(7)


async def test_a_response_in_another_serialization_fails_the_call(protocol: DubboProtocol, user_service, frame) -> None:
    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        header = await reader.readexactly(16)
        _, _, _, request_id, length = struct.unpack(">HBBqI", header)
        await reader.readexactly(length)
        body = hessian2.dumps_many([4, None, {}])
        writer.write(frame(23, request_id, body, status=20))
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.UserService")
        users = proxy(user_service, (await protocol.refer(url, dubbo.get_definition(user_service))).invoke)

        with pytest.raises(RpcError) as caught:
            await users.find("bob", 1)

    assert caught.value.status is Status.INTERNAL
    assert "serialization 23" in caught.value.message


async def test_connecting_takes_at_most_the_connect_timeout(protocol: DubboProtocol, user_service) -> None:
    # A listener that never answers the TLS handshake.
    async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener:
        port = listener.extra(SocketAttribute.local_port)
        url = URL.parse(
            f"dubbo://127.0.0.1:{port}/com.example.UserService"
            f"?ssl-enabled=true&ca-cert-file={_CERT_FILE}&tls-server-name=localhost&connect-timeout=100"
        )
        users = proxy(user_service, (await protocol.refer(url, dubbo.get_definition(user_service))).invoke)
        started = anyio.current_time()

        with pytest.raises(RpcError) as caught:
            await users.find("bob", 1)

    assert caught.value.status is Status.UNAVAILABLE
    assert anyio.current_time() - started == pytest.approx(0.1)
