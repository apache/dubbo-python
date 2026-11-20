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

from dubbo import Result, RpcError, Status
from dubbo.filter import chain_filters
from dubbo.filter.activecount import active_counts
from dubbo.filter.executes import ExecutesFilter

pytestmark = pytest.mark.anyio


async def test_executes_rejects_calls_above_the_method_limit_until_a_running_call_finishes(gate, call, url):
    invoker = chain_filters(gate, [ExecutesFilter(url.update_parameters({"executes": "5", "wait.executes": "1"}))])
    completed: list[Result] = []

    async def invoke() -> None:
        completed.append(await invoker.invoke(call("wait")))

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(invoke)
            await anyio.wait_all_tasks_blocked()
            refused = await invoker.invoke(call("wait"))
            other = await invoker.invoke(call("other"))
            gate.opened.set()
        after = await invoker.invoke(call("wait"))

    assert isinstance(refused.error, RpcError)
    assert (refused.error.status, refused.error.message) == (
        Status.UNAVAILABLE,
        "com.example.UserService.wait serves 1 calls at once",
    )
    assert (completed, other.value, after.value, gate.entered) == (
        [Result(value="wait")],
        "other",
        "wait",
        ["wait", "other", "wait"],
    )


async def test_executes_made_again_counts_the_calls_running_through_the_one_before(gate, call, url):
    before = chain_filters(gate, [ExecutesFilter(url.update_parameters({"executes": "2"}))])
    lowered = chain_filters(gate, [ExecutesFilter(url.update_parameters({"executes": "1"}))])

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(before.invoke, call("wait"))
            await anyio.wait_all_tasks_blocked()
            refused = await lowered.invoke(call("wait"))
            gate.opened.set()
        after = await lowered.invoke(call("wait"))

    assert isinstance(refused.error, RpcError)
    assert (refused.error.status, after.value, gate.entered) == (Status.UNAVAILABLE, "wait", ["wait", "wait"])


async def test_executes_counts_the_calls_served_apart_from_those_the_application_makes(gate, call, url):
    served = chain_filters(gate, [ExecutesFilter(url.update_parameters({"executes": "1"}))])

    with active_counts(url).counting(url, "wait"):
        result = await served.invoke(call("other"))
        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(served.invoke, call("wait"))
                await anyio.wait_all_tasks_blocked()
                refused = await served.invoke(call("wait"))
                gate.opened.set()

    assert result.value == "other"
    assert isinstance(refused.error, RpcError)
    assert gate.entered == ["other", "wait"]
