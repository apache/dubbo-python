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

from dubbo import Invocation, Invoker
from dubbo.cluster.router import RouterChain
from dubbo.extension import Resource

pytestmark = pytest.mark.anyio


@attrs.define(kw_only=True)
class _Keeping(Resource):
    hosts: set[str]
    events: list[str]
    name: str
    told: list[tuple[str | None, ...]] = attrs.field(factory=list)
    routed: list[tuple[str | None, ...]] = attrs.field(factory=list)

    def notify(self, invokers: Sequence[Invoker]) -> None:
        self.told.append(tuple(invoker.url.host for invoker in invokers))

    def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        self.routed.append(tuple(invoker.url.host for invoker in invokers))
        kept = [invoker for invoker in invokers if invoker.url.host in self.hosts]

        return invokers if len(kept) == len(invokers) else kept

    async def aclose(self) -> None:
        self.events.append(f"close {self.name}")

    async def __aenter__(self):
        self.events.append(f"open {self.name}")

        return self


async def test_a_nested_router_chain_notifies_every_router_and_routes_in_order(provider, call):
    a, b, c = provider("a"), provider("b"), provider("c")
    first = _Keeping(hosts={"a", "b"}, events=[], name="first")
    second = _Keeping(hosts={"b", "c"}, events=[], name="second")

    async with RouterChain([RouterChain([first]), second]) as chain:
        chain.notify((a, b, c))
        result = chain.route((a, b, c), call)

    assert result == [b]
    assert (first.told, second.told, first.routed, second.routed) == (
        [("a", "b", "c")],
        [("a", "b", "c")],
        [("a", "b", "c")],
        [("a", "b")],
    )


async def test_a_router_chain_opens_in_order_and_closes_in_reverse():
    events = []
    first = _Keeping(hosts=set(), events=events, name="first")
    second = _Keeping(hosts=set(), events=events, name="second")

    async with RouterChain([first, second]):
        assert events == ["open first", "open second"]

    assert events == ["open first", "open second", "close second", "close first"]


@pytest.mark.parametrize("has_router", [False, True], ids=["empty-chain", "unchanged-by-router"])
async def test_a_router_chain_preserves_the_candidate_sequence_when_no_provider_is_removed(has_router, provider, call):
    providers = (provider("a"), provider("b"))
    routers = [_Keeping(hosts={"a", "b"}, events=[], name="all")] if has_router else []

    async with RouterChain(routers) as chain:
        chain.notify(providers)

        assert chain.route(providers, call) is providers
