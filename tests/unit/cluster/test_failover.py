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

import attrs
import pytest

from dubbo import Invocation, Invoker, Result, RpcError, Status
from dubbo.cluster.directory import Directory
from dubbo.cluster.failover import FailoverCluster
from dubbo.exceptions import RemoteError
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_failover_retries_an_unavailable_call_on_an_untried_provider(provider, unavailable, open_cluster, call):
    down, up = provider("a", unavailable), provider("b", Result(value="ok"))

    async with open_cluster("failover", down, up) as cluster:
        result = await cluster.invoke(call)

    assert (result, down.calls, up.calls) == (Result(value="ok"), 1, 1)


@pytest.mark.parametrize(
    "error",
    [
        RpcError(Status.INVALID_ARGUMENT, "bad"),
        RemoteError("org.apache.dubbo.rpc.RpcException", "down", status=Status.UNAVAILABLE),
    ],
    ids=["invalid-argument", "remote-exception"],
)
async def test_failover_returns_non_retryable_errors_once(error, provider, open_cluster, call):
    failed = Result(error=error)
    remote = provider("a", failed, Result(value="ok"))

    async with open_cluster("failover", remote) as cluster:
        result = await cluster.invoke(call)

    assert (result, remote.calls) == (failed, 1)


@pytest.mark.parametrize(
    ("query", "attempts"),
    [("", 3), ("retries=0", 1), ("retries=4&greet.retries=1", 2)],
    ids=["default", "no-retry", "method-override"],
)
async def test_failover_makes_retries_plus_one_attempts(query, attempts, provider, unavailable, open_cluster, call):
    remote = provider("a", unavailable)

    async with open_cluster("failover", remote, query=query) as cluster:
        result = await cluster.invoke(call)

    assert (result, remote.calls) == (unavailable, attempts)


async def test_failover_does_not_retry_opening_a_stream(provider, unavailable, open_cluster, streaming_call):
    remote = provider("a", unavailable)

    async with open_cluster("failover", remote) as cluster:
        result = await cluster.invoke(streaming_call)

    assert (result, remote.calls) == (unavailable, 1)


@attrs.define(kw_only=True)
class _Changing(Directory):
    snapshots: tuple[tuple[Invoker, ...], ...]
    asked: int = 0

    def candidates(self, invocation: Invocation) -> Sequence[Invoker]:
        self.asked += 1

        return self.snapshots[min(self.asked, len(self.snapshots)) - 1]

    async def aclose(self) -> None:
        for snapshot in self.snapshots:
            for provider in snapshot:
                await provider.aclose()


async def test_failover_retries_on_a_provider_that_joined_after_the_first_attempt(provider, unavailable, call):
    down, joined = provider("a", unavailable), provider("b", Result(value="ok"))
    cluster = FailoverCluster(URL(protocol="consumer"), _Changing(snapshots=((down,), (joined,))))

    async with cluster:
        result = await cluster.invoke(call)

    assert (result, down.calls, joined.calls) == (Result(value="ok"), 1, 1)


async def test_failover_returns_the_last_failure_when_every_provider_left_before_the_retry(provider, unavailable, call):
    down = provider("a", unavailable)
    cluster = FailoverCluster(URL(protocol="consumer"), _Changing(snapshots=((down,), ())))

    async with cluster:
        result = await cluster.invoke(call)

    assert (result, down.calls) == (unavailable, 1)
