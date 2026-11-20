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

from collections.abc import Sequence
from contextlib import aclosing

import attrs
import pytest

from dubbo import Invocation, Invoker, Result, RpcError, Status
from dubbo.cluster import Cluster, LoadBalance, StaticDirectory, create_cluster
from dubbo.cluster.available import AvailableCluster
from dubbo.cluster.broadcast import BroadcastCluster
from dubbo.cluster.failback import FailbackCluster
from dubbo.cluster.failfast import FailfastCluster
from dubbo.cluster.failover import FailoverCluster
from dubbo.cluster.failsafe import FailsafeCluster
from dubbo.cluster.forking import ForkingCluster
from dubbo.extension import ExtensionError, extensions
from dubbo.url import URL

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("strategy", ["failfast", "failover"])
async def test_a_cluster_without_providers_returns_unavailable(strategy, open_cluster, call):
    async with open_cluster(strategy) as cluster:
        result = await cluster.invoke(call)

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message) == (
        Status.UNAVAILABLE,
        "no provider of test.Greeter is available",
    )


@pytest.mark.parametrize(
    ("name", "implementation"),
    [
        ("failfast", FailfastCluster),
        ("failover", FailoverCluster),
        ("available", AvailableCluster),
        ("broadcast", BroadcastCluster),
        ("failback", FailbackCluster),
        ("failsafe", FailsafeCluster),
        ("forking", ForkingCluster),
    ],
    ids=["failfast", "failover", "available", "broadcast", "failback", "failsafe", "forking"],
)
def test_cluster_strategies_are_installed(name, implementation):
    assert extensions.get(Cluster, name) is implementation


async def test_closing_a_cluster_closes_its_directory_providers(provider, open_cluster):
    first, second = provider("a"), provider("b")

    async with open_cluster("failfast", first, second):
        assert (first.closed, second.closed) == (False, False)

    assert (first.closed, second.closed) == (True, True)


async def test_a_cluster_can_call_and_close_another_cluster(provider, unavailable, call):
    down, up = provider("a", unavailable), provider("b", Result(value="ok"))
    inner = await create_cluster(URL.parse("consumer://h/test.Greeter?cluster=failfast"), StaticDirectory([down]))

    async with aclosing(
        await create_cluster(
            URL.parse("consumer://h/test.Greeter?cluster=failover&loadbalance=roundrobin"), StaticDirectory([inner, up])
        )
    ) as outer:
        result = await outer.invoke(call)

    assert (result, down.calls, up.calls, down.closed, up.closed) == (Result(value="ok"), 1, 1, True, True)


@pytest.mark.parametrize("strategy", ["failfast", "failover"])
async def test_a_cluster_calls_an_available_provider_before_an_unavailable_one(strategy, provider, open_cluster, call):
    down, up = provider("down", up=False), provider("up")

    async with open_cluster(strategy, down, up) as cluster:
        result = await cluster.invoke(call)

    assert (result.value, down.calls, up.calls) == ("up", 0, 1)


@pytest.mark.parametrize("strategy", ["failfast", "failover"])
async def test_a_cluster_calls_an_unavailable_provider_when_none_is_available(strategy, provider, open_cluster, call):
    first, second = provider("first", up=False), provider("second", up=False)

    async with open_cluster(strategy, first, second) as cluster:
        result = await cluster.invoke(call)

    assert (result.value, first.calls, second.calls) == ("first", 1, 0)


async def test_a_cluster_asks_only_the_provider_it_chooses_whether_it_is_available(provider, open_cluster, call):
    asked: list[str] = []

    class Asked(type(provider("a"))):
        @property
        def available(self) -> bool:
            asked.append(self.url.host)
            return self.up

    providers = [Asked(url=provider(host).url, results=(Result(value=host),)) for host in "abcd"]

    async with open_cluster("failfast", *providers) as cluster:
        result = await cluster.invoke(call)

    assert asked == [result.value]


async def test_a_cluster_passes_unchanged_candidates_to_its_load_balance(isolated_extensions, provider, call):
    seen: list[Sequence[Invoker]] = []

    class Recording:
        def __init__(self, url: URL) -> None:
            pass

        def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
            seen.append(invokers)
            return invokers[0]

    extensions.register(LoadBalance, "recording", Recording)
    directory = StaticDirectory([provider("a"), provider("b")])

    async with aclosing(
        await create_cluster(URL.parse("consumer://h/test.Greeter?cluster=failfast&loadbalance=recording"), directory)
    ) as cluster:
        await cluster.invoke(call)
        await cluster.invoke(call)

        assert seen[0] is seen[1] is directory.candidates(call)


async def test_a_cluster_reports_the_availability_of_its_directory(provider, open_cluster):
    remote = provider("a")

    async with open_cluster("failfast", remote) as cluster:
        assert cluster.available is True
        remote.up = False
        assert cluster.available is False


async def test_create_cluster_opens_the_strategy_named_by_the_url(provider):
    remote = provider("a")

    async with aclosing(
        await create_cluster(URL.parse("consumer://h/test.Greeter?cluster=failfast"), StaticDirectory([remote]))
    ) as cluster:
        assert isinstance(cluster, FailfastCluster)
        assert remote.closed is False

    assert remote.closed is True


async def test_create_cluster_closes_its_directory_when_the_strategy_cannot_be_loaded(provider):
    orphaned = provider("a")

    with pytest.raises(ExtensionError, match="'nope'"):
        await create_cluster(URL.parse("consumer://h/test.Greeter?cluster=nope"), StaticDirectory([orphaned]))

    assert orphaned.closed is True


async def test_a_method_uses_its_own_load_balance(isolated_extensions, provider, open_cluster, call, invocation):
    @attrs.define(kw_only=True)
    class Picking:
        index: int

        def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
            return invokers[self.index]

    extensions.register(LoadBalance, "first", lambda url: Picking(index=0))
    extensions.register(LoadBalance, "last", lambda url: Picking(index=-1))
    first, last = provider("a"), provider("b")

    async with open_cluster("failfast", first, last, query="loadbalance=first&greet.loadbalance=last") as cluster:
        await cluster.invoke(call)
        await cluster.invoke(invocation("other"))

    assert (first.calls, last.calls) == (1, 1)


async def test_a_sticky_reference_calls_the_provider_it_called_last(provider, open_cluster, call):
    first, second = provider("a"), provider("b")

    async with open_cluster("failfast", first, second, query="sticky=true") as cluster:
        for _ in range(3):
            await cluster.invoke(call)

    assert (first.calls, second.calls) == (3, 0)


async def test_a_sticky_reference_moves_on_when_its_provider_becomes_unavailable(provider, open_cluster, call):
    first, second = provider("a"), provider("b")

    async with open_cluster("failfast", first, second, query="sticky=true") as cluster:
        await cluster.invoke(call)
        first.up = False
        await cluster.invoke(call)
        first.up = True
        await cluster.invoke(call)

    assert (first.calls, second.calls) == (1, 2)


async def test_a_method_is_sticky_on_its_own(provider, open_cluster, call, invocation):
    first, second = provider("a"), provider("b")

    async with open_cluster("failfast", first, second, query="greet.sticky=true") as cluster:
        results = [(await cluster.invoke(call)).value for _ in range(2)]
        others = [(await cluster.invoke(invocation("other"))).value for _ in range(2)]

    assert (results, sorted(others)) == (["a", "a"], ["a", "b"])
