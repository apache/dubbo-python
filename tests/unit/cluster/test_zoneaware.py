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

from dubbo import RpcError, Status

pytestmark = pytest.mark.anyio


async def test_zone_aware_uses_the_preferred_registry_until_it_becomes_unavailable(provider, open_cluster, call):
    other, preferred = provider("a"), provider("b", query="registry.preferred=true")

    async with open_cluster("zone-aware", other, preferred) as cluster:
        assert (await cluster.invoke(call)).value == "b"
        preferred.up = False
        result = await cluster.invoke(call)

    assert (result.value, other.calls, preferred.calls) == ("a", 1, 1)


async def test_zone_aware_uses_the_registry_in_the_requested_zone(provider, open_cluster, invocation):
    east, west = provider("east", query="registry.zone=east"), provider("west", query="registry.zone=west")

    async with open_cluster("zone-aware", east, west) as cluster:
        result = await cluster.invoke(invocation(**{"registry.zone": "west"}))

    assert (result.value, east.calls, west.calls) == ("west", 0, 1)


async def test_zone_aware_falls_back_from_a_missing_zone(provider, open_cluster, invocation):
    east = provider("east", query="registry.zone=east")
    call = invocation(**{"registry.zone": "west", "registry.zone.force": "false"})

    async with open_cluster("zone-aware", east) as cluster:
        result = await cluster.invoke(call)

    assert (result.value, result.error, east.calls) == ("east", None, 1)


async def test_zone_aware_reports_a_missing_forced_zone_as_unavailable(provider, open_cluster, invocation):
    east = provider("east", query="registry.zone=east")
    call = invocation(**{"registry.zone": "west", "registry.zone.force": "true"})

    async with open_cluster("zone-aware", east) as cluster:
        result = await cluster.invoke(call)

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message, east.calls) == (
        Status.UNAVAILABLE,
        "no provider of test.Greeter is available in zone west",
        0,
    )


async def test_zone_aware_skips_zero_weight_and_unavailable_registries(provider, open_cluster, call):
    heavy, light, empty = provider("heavy"), provider("light", query="weight=0"), provider("empty", up=False)

    async with open_cluster("zone-aware", heavy, light, empty) as cluster:
        results = [await cluster.invoke(call) for _ in range(3)]

    assert ([result.value for result in results], heavy.calls, light.calls, empty.calls) == (["heavy"] * 3, 3, 0, 0)


async def test_zone_aware_returns_unavailable_when_every_registry_is_empty(provider, open_cluster, call):
    async with open_cluster("zone-aware", provider("a", up=False)) as cluster:
        result = await cluster.invoke(call)

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message) == (
        Status.UNAVAILABLE,
        "no provider of test.Greeter is available",
    )
