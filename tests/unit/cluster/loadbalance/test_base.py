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

import logging
from types import SimpleNamespace

import pytest

from dubbo.cluster import LoadBalance
from dubbo.cluster.loadbalance import base
from dubbo.cluster.loadbalance.base import PerSequence, Weights
from dubbo.cluster.loadbalance.consistenthash import ConsistentHashLoadBalance
from dubbo.cluster.loadbalance.leastactive import LeastActiveLoadBalance
from dubbo.cluster.loadbalance.random import RandomLoadBalance
from dubbo.cluster.loadbalance.roundrobin import RoundRobinLoadBalance
from dubbo.extension import extensions
from dubbo.url import URL


@pytest.mark.parametrize(
    ("name", "implementation"),
    [
        ("random", RandomLoadBalance),
        ("roundrobin", RoundRobinLoadBalance),
        ("leastactive", LeastActiveLoadBalance),
        ("consistenthash", ConsistentHashLoadBalance),
    ],
    ids=["random", "roundrobin", "leastactive", "consistenthash"],
)
def test_load_balances_are_installed(name, implementation):
    assert extensions.get(LoadBalance, name) is implementation


def test_per_sequence_keeps_what_it_derived_for_the_last_four_sequences_used(invokers):
    derived: list[tuple[int, str]] = []

    def derive(sequence, method):
        derived.append((len(sequence), method))
        return len(derived)

    kept = PerSequence(derive)
    sequences = [invokers(*[""] * size) for size in range(1, 6)]

    firsts = [kept.get(sequence, "greet") for sequence in sequences[:4]]
    again = [kept.get(sequence, "greet") for sequence in reversed(sequences[:4])]
    kept.get(sequences[4], "greet")
    evicted = kept.get(sequences[3], "greet")
    other = kept.get(sequences[0], "other")

    assert (firsts, again) == ([1, 2, 3, 4], [4, 3, 2, 1])
    assert (evicted, other) == (6, 7)
    assert derived[4:] == [(5, "greet"), (4, "greet"), (1, "other")]


@pytest.mark.parametrize(
    ("query", "now", "expected"),
    [
        ("?timestamp=1000&warmup=10000", 6.0, [50]),
        ("?timestamp=1000&warmup=10000&weight=10", 1.5, [1]),
        ("?timestamp=9000", 1.0, [1]),
        ("?timestamp=1000&warmup=10000", 11.0, [100]),
        ("", 6.0, [100]),
        ("?timestamp=9000&warmup=0", 1.0, [100]),
    ],
    ids=["half-warm", "at-least-one", "clock-behind", "warmup-finished", "no-timestamp", "no-warmup-clock-behind"],
)
def test_weights_increase_with_uptime_until_warmup_finishes(query, now, expected, monkeypatch, invokers):
    monkeypatch.setattr(base, "time", SimpleNamespace(time=lambda: now))

    assert Weights().get(invokers(query), "greet") == expected


def test_invalid_weights_use_the_default_and_log_a_warning(invokers, caplog):
    values = Weights().get(invokers("?weight=heavy", "?weight=100"), "greet")

    assert values == [100, 100]
    assert [(record.name, record.levelno) for record in caplog.records] == [
        ("dubbo.cluster.loadbalance.base", logging.WARNING)
    ]


def test_weights_reuse_the_same_list_until_the_provider_sequence_changes(invokers):
    weights = Weights()
    first, second = invokers("?weight=1", "?weight=2"), invokers("?weight=1", "?weight=2")

    initial = weights.get(first, "greet")
    assert weights.get(first, "greet") is initial
    changed = weights.get(second, "greet")

    assert initial == changed == [1, 2]
    assert changed is not initial
    assert weights.get(second, "greet") is changed


def test_weights_are_recomputed_for_the_same_providers_while_they_warm_up(monkeypatch, invokers):
    now = [1.0]
    monkeypatch.setattr(base, "time", SimpleNamespace(time=lambda: now[0]))
    weights = Weights()
    providers = invokers("?timestamp=1000&warmup=10000", "")
    initial = weights.get(providers, "greet")

    now[0] = 6.0
    warming = weights.get(providers, "greet")
    now[0] = 11.0
    warmed = weights.get(providers, "greet")

    assert (initial, warming, warmed) == ([1, 100], [50, 100], [100, 100])
    assert weights.get(providers, "greet") is warmed


def test_a_warming_provider_reads_its_settings_once_for_the_same_providers(monkeypatch, invokers):
    now = [1.0]
    monkeypatch.setattr(base, "time", SimpleNamespace(time=lambda: now[0]))
    read: list[str] = []
    get_parameter = URL.get_parameter

    def counted(self, key, *args):
        read.append(key)
        return get_parameter(self, key, *args)

    monkeypatch.setattr(URL, "get_parameter", counted)
    weights = Weights()
    providers = invokers("?timestamp=1000&warmup=10000")
    weights.get(providers, "greet")
    first = len(read)

    now[0] = 6.0
    warming = weights.get(providers, "greet")

    assert (warming, len(read)) == ([50], first)
