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
import contextlib

import anyio
import hessian2
import pytest

import dubbo
from dubbo import Method, Parameter, RpcError
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.rpc.client import proxy
from dubbo.rpc.definition import Service
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_disconnecting_a_caller_cancels_its_call_and_releases_its_capacity(protocol, impl, export, refer, frame):
    exporter = await export(protocol, impl, "?max-concurrent-calls=1")
    body = hessian2.dumps_many(("2.0.2", "com.example.UserService", "0.0.0", "sleep", "", {}))

    async with await anyio.connect_tcp("127.0.0.1", exporter.url.port) as stream:
        await stream.send(frame(0xC2, 5, body))
        await impl.started.wait()
    await impl.cancelled.wait()
    await anyio.wait_all_tasks_blocked()
    users = await refer(protocol, exporter)

    assert (await users.find("bob", 1)).name == "bob"
    assert not impl.released.is_set()


async def test_announcing_shutdown_makes_callers_turn_away(
    protocol: DubboProtocol, impl, export, find_invocation, user_service
) -> None:
    exporter = await export(protocol, impl)
    url = URL.parse(f"dubbo://127.0.0.1:{exporter.url.port}/com.example.UserService")
    invoker = await protocol.refer(url, dubbo.get_definition(user_service))
    await invoker.invoke(find_invocation(arguments=("bob", 1)))

    protocol.announce_shutdown()

    with anyio.fail_after(5):
        while invoker.available:
            await anyio.wait_all_tasks_blocked()


async def test_cancelling_export_closes_the_listener_it_opened(protocol, impl, monkeypatch, export):
    listeners = []
    started = anyio.Event()
    start_serving = asyncio.base_events.Server.start_serving

    async def start_and_wait(listener):
        listeners.append(listener)
        await start_serving(listener)
        started.set()
        await anyio.sleep_forever()

    monkeypatch.setattr(asyncio.base_events.Server, "start_serving", start_and_wait)
    scopes = []

    async def exporting():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await export(protocol, impl)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(exporting)
        await started.wait()
        scopes[0].cancel()

    assert len(listeners) == 1
    assert not listeners[0].is_serving()


async def test_a_failed_first_export_leaves_no_server_behind(protocol: DubboProtocol, impl, export) -> None:
    url = URL.parse("dubbo://127.0.0.1:0/com.example.Odd")
    odd = Service(
        interface="com.example.Odd",
        methods=(Method(name="take", request=(Parameter(name="z", type=complex),), response=None),),
    )
    with pytest.raises(TypeError, match="no Java type"):
        await protocol.export(url, odd, ServiceInvoker.from_implementation(impl, url))

    # A server left behind would refuse a service asking for other settings.
    exporter = await export(protocol, impl, "?payload=1024")

    assert exporter.url.port not in (None, 0)


@pytest.mark.parametrize(
    ("shared", "versions", "made"),
    [(True, ["", ""], 1), (True, ["1", "2"], 2), (False, ["", ""], 2)],
    ids=["shared", "per-version", "not-shared"],
)
async def test_references_share_codecs_only_of_a_serialization_that_says_so(
    protocol, impl, export, user_service, monkeypatch, shared, versions, made
) -> None:
    from dubbo.protocol.dubbo import invoker
    from dubbo.serialization.hessian2 import Hessian2Serialization

    calls = []
    from_definition = invoker.ServiceCodecs.from_definition

    def recording(serialization, definition, version):
        calls.append(version)
        return from_definition(serialization, definition, version)

    monkeypatch.setattr(invoker.ServiceCodecs, "from_definition", recording)
    monkeypatch.setattr(Hessian2Serialization, "shared", shared)
    exporter = await export(protocol, impl)

    for version, timeout in zip(versions, ("100", "200"), strict=True):
        url = URL.parse(f"dubbo://127.0.0.1:{exporter.url.port}/com.example.UserService?timeout={timeout}")
        url = url.update_parameters({"version": version}) if version else url
        users = proxy(user_service, (await protocol.refer(url, dubbo.get_definition(user_service))).invoke)
        # A call settles the connection, so that the server does not close while it accepts one.
        with contextlib.suppress(RpcError):
            await users.find("alice", hessian2.Long(1))

    assert len(calls) == made


async def test_a_host_name_that_port_0_binds_to_several_ports_is_refused(
    protocol: DubboProtocol, impl, user_service, monkeypatch
) -> None:
    class Socket:
        def __init__(self, host: str, port: int) -> None:
            self.address = (host, port)

        def getsockname(self):
            return self.address

    closed = []

    class Listener:
        def __init__(self) -> None:
            self.sockets = [Socket("127.0.0.1", 20881), Socket("::1", 20882)]

        def close(self) -> None:
            closed.append(self)

        async def wait_closed(self) -> None:
            pass

    async def create_server(*args, **kwargs):
        return Listener()

    monkeypatch.setattr(asyncio.get_running_loop(), "create_server", create_server)
    url = URL.parse("dubbo://localhost:0/com.example.UserService")

    with pytest.raises(ValueError, match="port 0 binds to different ports"):
        await protocol.export(url, dubbo.get_definition(user_service), ServiceInvoker.from_implementation(impl, url))

    assert len(closed) == 1
