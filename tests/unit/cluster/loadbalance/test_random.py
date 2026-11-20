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

import pytest

from dubbo.cluster.loadbalance.random import RandomLoadBalance
from dubbo.url import URL


def test_random_returns_a_single_provider_without_reading_its_weight(invokers, call, caplog):
    providers = invokers("?weight=heavy")

    chosen = RandomLoadBalance(URL(protocol="consumer")).select(providers, call)

    assert chosen is providers[0]
    assert caplog.records == []


def test_random_uses_the_weight_of_the_called_method(invokers, call, invocation):
    providers = invokers("?weight=100&greet.weight=0", "?weight=100")
    load_balance = RandomLoadBalance(URL(protocol="consumer"))

    assert {load_balance.select(providers, call).url.host for _ in range(200)} == {"10.0.0.2"}
    assert {load_balance.select(providers, invocation("other")).url.host for _ in range(200)} == {
        "10.0.0.1",
        "10.0.0.2",
    }


@pytest.mark.parametrize(
    ("queries", "share"),
    [
        (("?weight=100", "?weight=300"), 0.75),
        (("", "?weight=100"), 0.5),
        (("?weight=0", "?weight=0"), 0.5),
    ],
    ids=["weighted", "equal-default", "all-zero"],
)
def test_random_selects_providers_in_proportion_to_their_weights(queries, share, invokers, call):
    providers = invokers(*queries)
    load_balance = RandomLoadBalance(URL(protocol="consumer"))

    counts = Counter(load_balance.select(providers, call).url.host for _ in range(4000))

    assert counts["10.0.0.2"] / 4000 == pytest.approx(share, abs=0.03)


def test_random_never_selects_a_provider_of_weight_zero_beside_a_weighted_one(invokers, call):
    providers = invokers("?weight=0", "")
    load_balance = RandomLoadBalance(URL(protocol="consumer"))

    counts = Counter(load_balance.select(providers, call).url.host for _ in range(4000))

    assert counts == {"10.0.0.2": 4000}
