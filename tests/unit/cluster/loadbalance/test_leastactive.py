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

from collections import Counter
from contextlib import ExitStack

import pytest

from dubbo.cluster.loadbalance.leastactive import LeastActiveLoadBalance
from dubbo.extension import ApplicationScope
from dubbo.filter.activecount import ActiveCounts
from dubbo.rpc.invocation import Invoker
from dubbo.url import APPLICATION_SCOPE, URL


def _least_active(counts: ActiveCounts) -> LeastActiveLoadBalance:
    scope = ApplicationScope()
    scope.state[ActiveCounts] = counts
    return LeastActiveLoadBalance(URL(protocol="consumer", attributes={APPLICATION_SCOPE: scope}))


def _busy(stack: ExitStack, counts: ActiveCounts, provider: Invoker, calls: int, method: str = "greet") -> None:
    for _ in range(calls):
        stack.enter_context(counts.counting(provider.url, method))


def test_least_active_chooses_the_provider_with_the_fewest_calls_under_way_whatever_the_weights(invokers, call):
    with ExitStack() as stack:
        counts = ActiveCounts()
        providers = a, b, c = invokers("?weight=300", "?weight=100", "?weight=100")
        _busy(stack, counts, a, 5)
        _busy(stack, counts, b, 2)
        _busy(stack, counts, c, 3)
        _busy(stack, counts, b, 9, "other")

        assert _least_active(counts).select(providers, call) is b
        _busy(stack, counts, b, 2)
        assert _least_active(counts).select(providers, call) is c


def test_least_active_chooses_among_equally_busy_providers_in_proportion_to_their_weights(invokers, call):
    with ExitStack() as stack:
        counts = ActiveCounts()
        providers = a, b, _, d = invokers("?weight=100", "?weight=300", "?weight=0", "?weight=100")
        _busy(stack, counts, a, 2)
        _busy(stack, counts, b, 2)
        _busy(stack, counts, d, 3)
        load_balance = _least_active(counts)

        chosen = Counter(load_balance.select(providers, call).url.host for _ in range(4000))

        assert set(chosen) == {"10.0.0.1", "10.0.0.2"}
        assert chosen["10.0.0.2"] / 4000 == pytest.approx(0.75, abs=0.03)


def test_least_active_chooses_among_providers_that_all_weigh_zero(invokers, call):
    with ExitStack() as stack:
        counts = ActiveCounts()
        providers = a, b = invokers("?weight=0", "?weight=0")
        _busy(stack, counts, a, 1)

        assert _least_active(counts).select(providers, call) is b


def test_least_active_needs_the_application_that_keeps_the_counts():
    with pytest.raises(RuntimeError, match="belongs to no application"):
        LeastActiveLoadBalance(URL(protocol="consumer"))
