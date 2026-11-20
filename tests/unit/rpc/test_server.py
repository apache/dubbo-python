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

import dubbo
from dubbo import Invocation, Method, Parameter, Result, RpcError, RpcType, Service, Status
from dubbo.filter import chain_filters
from dubbo.rpc.context import serving
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_service_invoker_returns_the_handler_value_and_response_attachments():
    async def rename(id: int, name: str) -> str:
        call = dubbo.incoming()
        call.response_attachments["audit-id"] = str(id)
        return f"{name}@{call.attachments['operator']}"

    method = Method(
        name="rename",
        request=(Parameter(name="id", type=int), Parameter(name="name", type=str)),
        response=str,
        handler=rename,
    )
    invoker = ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,)))
    invocation = Invocation(
        interface="Users", method="rename", definition=method, arguments=(7, "b"), attachments={"operator": "alice"}
    )

    with serving(invocation.attachments, peer=None):
        result = await invoker.invoke(invocation)

    assert result == Result(value="b@alice", attachments={"audit-id": "7"})


@pytest.mark.parametrize(
    ("name", "arguments", "status", "message"),
    [
        ("find", ("g", 1), Status.UNIMPLEMENTED, "Users has no method 'find'"),
        ("findByName", ("g",), Status.INVALID_ARGUMENT, "findByName() takes 2 arguments, not 1"),
    ],
    ids=["python-name-is-not-wire-name", "missing-argument"],
)
async def test_service_invoker_rejects_calls_that_do_not_match_its_served_method(name, arguments, status, message):
    async def find(name: str, limit: int) -> list[str]:
        pytest.fail("a rejected call must not reach the handler")

    method = Method(
        name="findByName",
        request=(Parameter(name="name", type=str), Parameter(name="limit", type=int)),
        response=list[str],
        handler=find,
    )
    invoker = ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,)))

    result = await invoker.invoke(Invocation(interface="Users", method=name, definition=method, arguments=arguments))

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message) == (status, message)


@pytest.mark.parametrize(
    "error",
    [RpcError(Status.PERMISSION_DENIED, "operator required"), ValueError("broken")],
    ids=["rpc-error", "handler-exception"],
)
async def test_service_invoker_returns_the_handler_error_with_its_response_attachments(error):
    async def fail() -> None:
        dubbo.incoming().response_attachments["audit-id"] = "7"
        raise error

    method = Method(name="fail", request=(), response=None, handler=fail)
    invoker = ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,)))

    with serving({}, peer=None):
        result = await invoker.invoke(Invocation(interface="Users", method="fail", definition=method))

    assert result == Result(error=error, attachments={"audit-id": "7"})


async def test_service_invoker_propagates_cancellation_to_the_handler():
    cancelled = anyio.Event()

    async def wait() -> None:
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.set()

    method = Method(name="wait", request=(), response=None, handler=wait)
    invoker = ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,)))

    with pytest.raises(TimeoutError), anyio.fail_after(0), serving({}, peer=None):
        await invoker.invoke(Invocation(interface="Users", method="wait", definition=method))

    assert cancelled.is_set()


async def test_serving_filters_complete_only_after_the_stream_handler_returns():
    entered, release, finished = anyio.Event(), anyio.Event(), []

    class Record:
        async def invoke(self, call_next, invocation):
            result = await call_next(invocation)
            finished.append(invocation.method)
            return result

    async def watch(query: str, stream: dubbo.SendStream[int]) -> None:
        entered.set()
        await release.wait()

    method = Method(
        name="watch",
        rpc_type=RpcType.SERVER_STREAM,
        request=(Parameter(name="query", type=str),),
        response=int,
        handler=watch,
    )
    invoker = chain_filters(
        ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,))), [Record()]
    )

    class Sink(dubbo.SendStream[int]):
        async def send(self, message: int) -> None:
            pass

    with anyio.fail_after(5), serving({}, peer=None):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(
                invoker.invoke,
                Invocation(interface="Users", method="watch", definition=method, arguments=("2", Sink())),
            )
            await entered.wait()
            assert finished == []
            release.set()

    assert finished == ["watch"]


@pytest.mark.parametrize(
    ("raised", "logged"),
    [(AttributeError("a bug in the handler"), True), (RpcError(Status.NOT_FOUND, "no such user"), False)],
    ids=["unexpected", "chosen-status"],
)
async def test_a_handler_failure_reaches_the_caller_and_only_an_unexpected_one_is_logged(raised, logged, caplog):
    async def rename(id: int) -> str:
        raise raised

    method = Method(name="rename", request=(Parameter(name="id", type=int),), response=str, handler=rename)
    invoker = ServiceInvoker(url=URL(protocol="local"), service=Service(interface="Users", methods=(method,)))
    invocation = Invocation(interface="Users", method="rename", definition=method, arguments=(7,))

    with serving(invocation.attachments, peer=None):
        result = await invoker.invoke(invocation)

    assert result.error is raised
    records = [record for record in caplog.records if record.name == "dubbo.rpc.server"]
    assert [(record.levelname, record.exc_info[1]) for record in records] == ([("ERROR", raised)] if logged else [])
