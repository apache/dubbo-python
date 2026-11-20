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

import typing
from contextlib import aclosing

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo.cluster import create_cluster
from dubbo.cluster.directory import StaticDirectory
from dubbo.protocol.triple import TripleProtocol
from dubbo.rpc.client import proxy
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_export_reports_the_bound_port(protocol: TripleProtocol, impl, export) -> None:
    exporter = await export(protocol, impl)

    assert exporter.url.port not in (None, 0)
    assert exporter.url.path == "test.Echo"


async def test_group_and_version_must_match_exactly(
    protocol: TripleProtocol, export, serve, refer, echo_impl_type
) -> None:
    one, two = echo_impl_type(), echo_impl_type()
    first = await export(protocol, one, "?group=a&version=1.0")
    await serve(protocol, URL.parse(f"tri://127.0.0.1:{first.url.port}/test.Echo?group=a&version=2.0"), two)

    with dubbo.outgoing({"Tenant": "v1"}):
        assert await (await refer(protocol, first, "?group=a&version=1.0")).say(StringValue(value="x")) == StringValue(
            value="x|v1"
        )
    with dubbo.outgoing({"Tenant": "v2"}):
        assert await (await refer(protocol, first, "?group=a&version=2.0")).say(StringValue(value="x")) == StringValue(
            value="x|v2"
        )
    with pytest.raises(RpcError, match="UNIMPLEMENTED"):
        await (await refer(protocol, first, "?group=a")).say(StringValue(value="x"))


@dubbo.service("test.Plain")
class _Plain(typing.Protocol):
    async def say(self, text: str) -> str: ...


async def test_export_rejects_a_taken_route(protocol: TripleProtocol, export, serve, echo_impl_type) -> None:
    exporter = await export(protocol, echo_impl_type())
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo")

    with pytest.raises(ValueError, match="already exported"):
        await serve(protocol, url, echo_impl_type())


async def test_export_rejects_a_contract_its_serialization_cannot_carry(
    protocol: TripleProtocol, export, serve, echo_impl_type
) -> None:
    exporter = await export(protocol, echo_impl_type())
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo")

    with pytest.raises(TypeError, match="protobuf carries messages"):
        await serve(protocol, url, echo_impl_type(), _Plain)


async def test_a_failed_first_export_leaves_no_server_behind(protocol: TripleProtocol, serve, echo_impl_type) -> None:
    with pytest.raises(TypeError, match="protobuf carries messages"):
        await serve(protocol, URL.parse("tri://127.0.0.1:0/test.Echo"), echo_impl_type(), _Plain)

    # A server left behind would refuse a service asking for other settings.
    url = URL.parse("tri://127.0.0.1:0/test.Echo?triple.max-receive-message-size=1024")
    exporter = await serve(protocol, url, echo_impl_type())

    assert exporter.url.port not in (None, 0)


async def test_closing_an_exporter_waits_for_running_calls(
    protocol: TripleProtocol, impl, export, serve, refer, echo_impl_type
) -> None:
    exporter = await export(protocol, impl)
    echo = await refer(protocol, exporter)
    other = await serve(
        protocol, URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo?version=2"), echo_impl_type()
    )
    results: list[StringValue] = []

    async with anyio.create_task_group() as tasks:

        async def call() -> None:
            results.append(await echo.say(StringValue(value="wait")))

        tasks.start_soon(call)
        await impl.started.wait()
        tasks.start_soon(exporter.aclose)
        await anyio.wait_all_tasks_blocked()

        with pytest.raises(RpcError, match="UNAVAILABLE"):
            await echo.say(StringValue(value="x"))
        assert results == []
        impl.release.set()

    assert results == [StringValue(value="wait|-")]
    assert await (await refer(protocol, other, "?version=2")).say(StringValue(value="x")) == StringValue(value="x|-")


async def test_calls_move_to_another_provider_while_one_is_unexported(
    protocol: TripleProtocol, impl, export, refer, echo_contract, echo_impl_type
) -> None:
    leaving = await export(protocol, impl)
    async with TripleProtocol() as other:
        staying = await export(other, echo_impl_type())
        url = URL.parse("tri://127.0.0.1/test.Echo")
        invokers = [
            await protocol.refer(url.replace(port=exporter.url.port), dubbo.get_definition(echo_contract))
            for exporter in (leaving, staying)
        ]
        async with aclosing(await create_cluster(url, StaticDirectory(invokers))) as cluster:
            echo = proxy(echo_contract, cluster.invoke)
            direct = await refer(protocol, leaving)
            replies: list[StringValue] = []

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(direct.say, StringValue(value="wait"))
                await impl.started.wait()
                tasks.start_soon(leaving.aclose)
                await anyio.wait_all_tasks_blocked()

                replies = [await echo.say(StringValue(value=str(i))) for i in range(20)]
                impl.release.set()

    assert replies == [StringValue(value=f"{i}|-") for i in range(20)]


async def test_closing_an_exporter_cancels_the_calls_still_running_after_shutwait(
    protocol: TripleProtocol, impl, export, refer
) -> None:
    exporter = await export(protocol, impl, "?shutwait=50")
    echo = await refer(protocol, exporter)
    errors: list[RpcError] = []

    async with anyio.create_task_group() as tasks:

        async def call() -> None:
            with pytest.raises(RpcError) as raised:
                await echo.say(StringValue(value="sleep"))
            errors.append(raised.value)

        tasks.start_soon(call)
        await impl.started.wait()
        with anyio.fail_after(2):
            await exporter.aclose()

    assert impl.cancelled.is_set()
    assert [error.status for error in errors] == [Status.CANCELLED]


async def test_an_export_to_a_served_address_asks_for_the_settings_of_its_server(
    protocol: TripleProtocol, export, serve, echo_impl_type
) -> None:
    exporter = await export(protocol, echo_impl_type())
    address = f"tri://127.0.0.1:{exporter.url.port}/test.Echo"

    with pytest.raises(ValueError, match="runs with other max-receive-message-size, shutwait"):
        await serve(protocol, URL.parse(f"{address}?triple.max-receive-message-size=8&shutwait=1"), echo_impl_type())


async def test_services_of_one_server_may_differ_in_service_parameters(
    protocol: TripleProtocol, export, serve, echo_impl_type
) -> None:
    exporter = await export(protocol, echo_impl_type())
    address = f"tri://127.0.0.1:{exporter.url.port}/test.Echo"

    await serve(
        protocol, URL.parse(f"{address}?version=2&timeout=100&say.timeout=50&application=other"), echo_impl_type()
    )
    await serve(protocol, URL.parse(f"{address}?version=3&weight=10&warmup=1000&dubbo.tag=gray"), echo_impl_type())


# Windows refuses the connection after its own retries, in real time.
@pytest.mark.real_clock
async def test_the_server_listens_until_the_protocol_closes(impl, export, refer, echo_contract) -> None:
    async with TripleProtocol() as protocol:
        exporter = await export(protocol, impl)
        await exporter.aclose()
        port = exporter.url.port

        with pytest.raises(RpcError, match=r"UNAVAILABLE: .* is no longer served here"):
            await (await refer(protocol, exporter)).say(StringValue(value="x"))

    # Windows takes about two seconds to refuse a connection, longer than the default timeout.
    url = URL.parse(f"tri://127.0.0.1:{port}/test.Echo?timeout=5000")
    async with TripleProtocol() as caller:
        with pytest.raises(RpcError, match="UNAVAILABLE"):
            await proxy(echo_contract, (await caller.refer(url, dubbo.get_definition(echo_contract))).invoke).say(
                StringValue(value="x")
            )


async def test_an_invoker_that_cannot_be_created_gives_its_connection_back(
    protocol: TripleProtocol, impl, export, echo_contract
) -> None:
    exporter = await export(protocol, impl)
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/test.Echo")
    invoker = await protocol.refer(url, dubbo.get_definition(echo_contract))

    with pytest.raises(ValueError, match="compressor"):
        await protocol.refer(
            url.update_parameters({"triple.compressor": "missing"}), dubbo.get_definition(echo_contract)
        )
    await invoker.aclose()

    assert protocol._clients._shares == {}
