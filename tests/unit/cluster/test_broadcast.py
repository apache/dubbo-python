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

import pytest

from dubbo import Result, RpcError, Status

pytestmark = pytest.mark.anyio


async def test_broadcast_calls_every_provider_and_returns_the_last_result(provider, open_cluster, call):
    first, middle, last = provider("a"), provider("b"), provider("c")

    async with open_cluster("broadcast", first, middle, last) as cluster:
        result = await cluster.invoke(call)

    assert (result, first.calls, middle.calls, last.calls) == (Result(value="c"), 1, 1, 1)


async def test_broadcast_calls_every_provider_and_returns_the_last_failure(provider, open_cluster, call):
    failed = Result(error=RpcError(Status.INVALID_ARGUMENT, "bad"))
    first = provider("a", Result(error=RpcError(Status.UNAVAILABLE, "down")))
    middle, last = provider("b", failed), provider("c")

    async with open_cluster("broadcast", first, middle, last) as cluster:
        result = await cluster.invoke(call)

    assert (result, first.calls, middle.calls, last.calls) == (failed, 1, 1, 1)


@pytest.mark.parametrize(
    ("percent", "calls"),
    [("50", [1, 1, 0, 0]), ("0", [1, 1, 1, 1]), ("100", [1, 1, 1, 1])],
    ids=["half", "zero-means-all", "all"],
)
async def test_broadcast_stops_when_the_configured_share_of_providers_has_failed(
    percent, calls, provider, unavailable, open_cluster, call
):
    providers = [provider(host, unavailable) for host in "abcd"]

    async with open_cluster("broadcast", *providers, query=f"broadcast.fail.percent={percent}") as cluster:
        result = await cluster.invoke(call)

    assert (result, [remote.calls for remote in providers]) == (unavailable, calls)


async def test_broadcast_refuses_a_failure_share_above_one_hundred(open_cluster):
    with pytest.raises(ValueError, match="between 0 and 100"):
        async with open_cluster("broadcast", query="broadcast.fail.percent=101"):
            pass


async def test_broadcast_opens_a_stream_on_one_provider(provider, open_cluster, streaming_call):
    first, second = provider("a"), provider("b")

    async with open_cluster("broadcast", first, second) as cluster:
        result = await cluster.invoke(streaming_call)

    assert (result, first.calls, second.calls) == (Result(value="a"), 1, 0)
