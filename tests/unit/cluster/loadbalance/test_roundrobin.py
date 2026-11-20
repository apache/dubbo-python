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

from dubbo.cluster import LoadBalance
from dubbo.cluster.loadbalance.roundrobin import RoundRobinLoadBalance
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL


def _turns(load_balance: LoadBalance, providers: tuple[Invoker, ...], times: int, call: Invocation) -> str:
    # The provider at 10.0.0.1 is a, the one at 10.0.0.2 is b, and so on.
    return "".join("abcdefgh"[int(str(load_balance.select(providers, call).url.host)[-1]) - 1] for _ in range(times))


def test_round_robin_spreads_the_turns_of_heavier_providers_as_nginx_does(invokers, call):
    providers = invokers("?weight=5", "?weight=1", "?weight=1")

    assert _turns(RoundRobinLoadBalance(URL(protocol="consumer")), providers, 14, call) == "aabacaa" * 2


@pytest.mark.parametrize(
    ("queries", "turns"),
    [
        (("", "", ""), "abcabc"),
        (("?weight=0", "", "?greet.weight=0"), "bbbbbb"),
        (("?weight=0", "?weight=0"), "ababab"),
    ],
    ids=["equal-default-weights", "zero-method-and-provider-weights", "all-zero-weights"],
)
def test_round_robin_skips_providers_of_weight_zero_unless_all_weigh_zero(queries, turns, invokers, call):
    load_balance = RoundRobinLoadBalance(URL(protocol="consumer"))

    assert _turns(load_balance, invokers(*queries), len(turns), call) == turns


def test_round_robin_keeps_the_turns_of_providers_while_the_invokers_change(invokers, call):
    a, b, c = invokers("?weight=2", "?weight=1", "?weight=1")
    load_balance = RoundRobinLoadBalance(URL(protocol="consumer"))

    assert _turns(load_balance, (a, b), 2, call) == "ab"
    # a and b keep what they gained, 1 and -1, and c starts at none.
    assert _turns(load_balance, (b, a, c), 4, call) == "acab"


def test_round_robin_spreads_each_set_of_providers_that_routing_alternates_between(invokers, call):
    a, b, c, d = invokers("", "", "", "")
    load_balance = RoundRobinLoadBalance(URL(protocol="consumer"))
    sets = ((a, c), (b, d))

    chosen = [load_balance.select(sets[index % 2], call) for index in range(8)]

    assert chosen == [a, b, c, d] * 2
