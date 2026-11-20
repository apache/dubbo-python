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

from contextlib import aclosing

import anyio
import pytest

from dubbo import Invocation, Invoker, RemoteError, Result, RpcError, Status
from dubbo.cluster import StaticDirectory, create_cluster
from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "answer",
    [Result(value="ok"), Result(error=RemoteError("java.lang.IllegalStateException", "bad"))],
    ids=["value", "remote-exception"],
)
async def test_forking_returns_the_first_answer_and_cancels_unanswered_calls(
    answer, provider, unavailable, open_cluster, call
):
    started, cancelled = anyio.Event(), anyio.Event()

    class Hanging(Invoker):
        url = URL(protocol="tri", host="hanging")

        async def invoke(self, invocation: Invocation) -> Result:
            started.set()
            try:
                await anyio.sleep_forever()
            finally:
                cancelled.set()

        async def aclose(self) -> None:
            pass

    class Answering(Invoker):
        url = URL(protocol="tri", host="answering")

        async def invoke(self, invocation: Invocation) -> Result:
            await started.wait()
            return answer

        async def aclose(self) -> None:
            pass

    async with open_cluster(
        "forking", Hanging(), provider("failed", unavailable), Answering(), query="forks=3"
    ) as cluster:
        result = await cluster.invoke(call)

    assert result is answer
    assert cancelled.is_set()


async def test_forking_returns_the_last_failure_when_no_provider_answers(provider, unavailable, open_cluster, call):
    failed = Result(error=RpcError(Status.INVALID_ARGUMENT, "bad"))

    async with open_cluster("forking", provider("a", unavailable), provider("b", failed)) as cluster:
        result = await cluster.invoke(call)

    assert result is failed


@pytest.mark.parametrize(
    ("query", "calls"),
    [("", 2), ("forks=2", 2), ("forks=1", 1), ("forks=0", 4), ("forks=9", 4)],
    ids=["default", "two", "one", "zero-means-all", "above-provider-count"],
)
async def test_forking_calls_the_configured_number_of_distinct_providers(
    query, calls, provider, unavailable, open_cluster, call
):
    providers = [provider(host, unavailable) for host in "abcd"]

    async with open_cluster("forking", *providers, query=query) as cluster:
        result = await cluster.invoke(call)

    assert result is unavailable
    assert sorted(remote.calls for remote in providers) == [0] * (4 - calls) + [1] * calls


async def test_forking_opens_a_stream_on_one_provider(provider, open_cluster, streaming_call):
    first, second = provider("a"), provider("b")

    async with open_cluster("forking", first, second) as cluster:
        result = await cluster.invoke(streaming_call)

    assert (result, first.calls, second.calls) == (Result(value="a"), 1, 0)


@pytest.mark.parametrize("load_balance", ["random", "roundrobin", "leastactive", "consistenthash"])
async def test_forking_calls_distinct_providers_on_every_call_whatever_the_load_balance(
    load_balance, provider, unavailable, call
):
    providers = [
        provider(host, unavailable, query=f"weight={weight}") for host, weight in (("a", 1), ("b", 2), ("c", 3))
    ]
    query = f"cluster=forking&forks=2&loadbalance={load_balance}"

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            url = URL.parse(f"consumer://127.0.0.1/test.Greeter?{query}").replace(attributes={APPLICATION_SCOPE: scope})
            async with aclosing(await create_cluster(url, StaticDirectory(providers))) as cluster:
                results = [await cluster.invoke(call) for _ in range(3)]

    assert results == [unavailable] * 3
    assert sum(remote.calls for remote in providers) == 6
