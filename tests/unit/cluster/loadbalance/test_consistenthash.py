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

import json
from pathlib import Path

import attrs
import pytest

from dubbo.cluster import LoadBalance
from dubbo.cluster.loadbalance.consistenthash import ConsistentHashLoadBalance
from dubbo.rpc.invocation import Invoker
from dubbo.url import URL


@pytest.fixture
def providers(invokers):
    return invokers("", "", "", port=20880)


@pytest.fixture
def hashed(providers, call):
    def select(load_balance: LoadBalance, *arguments: object, candidates: tuple[Invoker, ...] = providers) -> str:
        chosen = load_balance.select(candidates, attrs.evolve(call, arguments=arguments))

        return str(chosen.url.host)[-1]

    return select


@pytest.mark.parametrize("query", ["", "?hash.nodes=8"], ids=["default-nodes", "eight-nodes"])
def test_consistent_hash_preserves_the_recorded_dubbo_key_assignments(query, hashed):
    cases = json.loads((Path(__file__).parent / "data" / "consistenthash.json").read_text())[query]
    load_balance = ConsistentHashLoadBalance(URL.parse(f"consumer://h/test.Greeter{query}"))

    chosen = {argument: hashed(load_balance, int(argument) if argument.isdigit() else argument) for argument in cases}

    assert chosen == cases


@pytest.mark.parametrize(
    ("query", "arguments", "key"),
    [
        ("?hash.arguments=1", ("ignored", "alice"), ("alice",)),
        ("?hash.arguments=0,1,5", ("al", "ice"), ("alice",)),
        ("?greet.hash.arguments=1", ("x", "bob"), ("bob",)),
        ("?hash.arguments=-1", ("alice",), ()),
        ("", (None,), ("null",)),
        ("", (True,), ("true",)),
    ],
    ids=["second-argument", "joined-and-out-of-range", "method-override", "negative-index", "null", "boolean"],
)
def test_consistent_hash_builds_the_key_from_the_selected_arguments(query, arguments, key, hashed):
    selected = ConsistentHashLoadBalance(URL.parse(f"consumer://h/test.Greeter{query}"))
    default = ConsistentHashLoadBalance(URL(protocol="consumer"))

    assert hashed(selected, *arguments) == hashed(default, *key)


def test_consistent_hash_moves_only_the_keys_of_a_provider_that_leaves(hashed, providers):
    load_balance = ConsistentHashLoadBalance(URL(protocol="consumer"))
    keys = [f"key{index}" for index in range(300)]
    before = {key: hashed(load_balance, key) for key in keys}

    after = {key: hashed(load_balance, key, candidates=providers[:2]) for key in keys}

    assert {key: host for key, host in before.items() if host != "3"} == {
        key: host for key, host in after.items() if before[key] != "3"
    }
    assert set(after.values()) == {"1", "2"}


@pytest.mark.parametrize(
    ("query", "message"),
    [("?hash.nodes=3", "at least 4"), ("?greet.hash.nodes=0", "at least 4"), ("?hash.arguments=first", "first")],
    ids=["too-few-nodes", "method-nodes", "non-integer-index"],
)
def test_consistent_hash_refuses_invalid_settings(query, message):
    with pytest.raises(ValueError, match=message):
        ConsistentHashLoadBalance(URL.parse(f"consumer://h/test.Greeter{query}"))
