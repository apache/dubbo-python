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
import logging
import re

import anyio
import attrs
import pytest

from dubbo import Method, Parameter
from dubbo.cluster.router.condition import ConditionRouter
from dubbo.url import PROVIDER_URL, URL

pytestmark = pytest.mark.anyio

CONSUMER = "consumer://10.0.0.1/test.Greeter?application=web&version=1.0"


async def test_condition_rules_of_the_service_and_the_consumer_apply_in_turn(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1"), provider("10.0.0.2", "zone=x"), provider("10.0.0.3", "zone=x")
    providers = (a, b, c)
    config_store.put("test.Greeter:1.0:.condition-router", "conditions: ['method = greet => zone = x']")
    config_store.put("web.condition-router", "conditions: ['=> host != 10.0.0.3']")

    async with routed(ConditionRouter) as router:
        router.notify(providers)

        assert router.route(providers, invocation()) == [b]
        assert router.route(providers, invocation("other")) == [a, b]


async def test_a_condition_routes_to_the_same_sequence_while_the_providers_do_not_change(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1"), provider("10.0.0.2", "zone=x"), provider("10.0.0.3", "zone=x")
    providers = (a, b, c)
    config_store.put("test.Greeter:1.0:.condition-router", "conditions: ['method = greet => zone = x']")

    async with routed(ConditionRouter) as router:
        router.notify(providers)
        first = router.route(providers, invocation())
        other = router.route(providers, invocation("other"))
        again = router.route(providers, invocation())
        changed = (a, b)
        router.notify(changed)
        after = router.route(changed, invocation())

    assert (first, other, after) == ([b, c], providers, [b])
    assert again is first


async def test_a_condition_without_then_blocks_and_one_matching_nothing_keeps_unless_forced(
    config_store, provider, invocation, routed
):
    a = provider("10.0.0.1", "zone=x")
    key = "test.Greeter:1.0:.condition-router"
    config_store.put(key, "conditions: ['host = 10.0.0.1 => ', 'method = greet => zone = y']")

    async with routed(ConditionRouter) as router:
        assert router.route((a,), invocation()) == ()

        config_store.put(key, "conditions: ['method = greet => zone = y']")
        await anyio.wait_all_tasks_blocked()
        assert router.route((a,), invocation()) == (a,)

        config_store.put(key, "force: true\nconditions: ['method = greet => zone = y']")
        await anyio.wait_all_tasks_blocked()
        assert router.route((a,), invocation()) == ()


async def test_a_condition_rule_of_the_provider_application_follows_the_providers(
    config_store, provider, invocation, routed
):
    a, b = provider("10.0.0.1"), provider("10.0.0.2", "version=1.0")
    config_store.put("greeter.condition-router", "conditions: ['=> version = $version & provider.host = 10.0.0.*']")

    async with routed(ConditionRouter) as router:
        router.notify((a, b))
        await anyio.wait_all_tasks_blocked()

        assert router.route((a, b), invocation()) == [b]


async def test_the_rules_of_provider_applications_route_to_the_same_sequence_while_the_providers_do_not_change(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1"), provider("10.0.0.2", "zone=x"), provider("10.0.0.3", app="other")
    providers = (a, b, c)
    config_store.put("greeter.condition-router", "conditions: ['=> zone = x']")

    async with routed(ConditionRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()
        first = router.route(providers, invocation())
        again = router.route(providers, invocation())

    assert first == [b, c]
    assert again is first


async def test_the_condition_rule_of_each_provider_application_routes_its_own_providers(
    config_store, provider, invocation, routed
):
    a1, a2 = provider("10.0.0.1"), provider("10.0.0.2")
    b1, b2 = provider("10.0.0.3", app="other"), provider("10.0.0.4", app="other")
    c1 = provider("10.0.0.5", app="third")
    providers = (a1, a2, b1, b2, c1)
    config_store.put("greeter.condition-router", "conditions: ['=> host = 10.0.0.1']")
    config_store.put("other.condition-router", "conditions: ['=> host = 10.0.0.4']")

    async with routed(ConditionRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()

        assert router.route(providers, invocation()) == [a1, b2, c1]

        # Another order of the same providers keeps the rules, even before anything is read.
        router.notify(providers[::-1])
        assert router.route(providers, invocation()) == [a1, b2, c1]

        # The rules of an application without providers stop applying.
        router.notify((b1, b2))
        await anyio.wait_all_tasks_blocked()
        assert router.route(providers, invocation()) == [a1, a2, b2, c1]


async def test_a_v3_1_condition_goes_to_one_destination_by_weight(config_store, provider, invocation, routed):
    a, b = provider("10.0.0.1", "zone=x"), provider("10.0.0.2", "zone=y")
    config_store.put(
        "web.condition-router",
        "configVersion: v3.1\nconditions:\n"
        "  - from: {match: 'attachments[user] = 1~9'}\n"
        "    to: [{match: 'zone = x', weight: 1}, {match: 'zone = z'}]\n"
        "  - from: {match: 'method = block'}\n"
        "    to: []\n",
    )

    async with routed(ConditionRouter) as router:
        assert router.route((a, b), invocation(user="5")) == [a]
        assert router.route((a, b), invocation(user="10")) == (a, b)
        assert router.route((a, b), invocation("block")) == ()


async def test_condition_values_match_as_dubbo_globs_ranges_values_of_the_reference_and_argument_text(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1", "zone=x1"), provider("10.0.0.2", "zone=y1"), provider("10.0.0.3", "zone=u[12]")
    providers = (a, b, c)
    key = "test.Greeter:1.0:.condition-router"
    long_number = attrs.evolve(
        invocation(),
        definition=Method(name="greet", request=(Parameter(name="number", type=str),), response=None),
        arguments=("9" * 5000,),
    )

    async with routed(ConditionRouter, f"{CONSUMER}&zone=x*") as router:
        for condition, call, routed in [
            ("=> zone = $zone", invocation(), [a]),
            ("=> zone = u[12]", invocation(), [c]),
            ("=> zone = *1", invocation(), [a, b]),
            ("host = $host => zone = y1", invocation(), providers),
            ("arguments[0] = 1~9 => zone = y1", long_number, providers),
            ("arguments[0] = true => zone = y1", invocation(arguments=(True,)), [b]),
            ("arguments[0] = null => zone = y1", invocation(arguments=(None,)), [b]),
        ]:
            config_store.put(key, f"force: true\nconditions: ['{condition}']")
            await anyio.wait_all_tasks_blocked()
            assert list(router.route(providers, call)) == list(routed), condition


async def test_a_condition_names_providers_by_what_they_published_not_by_the_settings_of_the_calls(
    config_store, provider, invocation, routed
):
    def called(host: str, zone: str):
        # The URL a consumer of zone hz calls with, whose parameters replace those the provider published.
        published = URL.parse(f"tri://{host}:20880/test.Greeter?zone={zone}")
        remote = provider(host)
        remote.url = published.update_parameters({"zone": "hz"}).replace(attributes={PROVIDER_URL: published})

        return remote

    near, far = called("10.0.0.1", "hz"), called("10.0.0.2", "sh")
    config_store.put("test.Greeter:1.0:.condition-router", "force: true\nconditions: ['=> zone = $zone']")

    async with routed(ConditionRouter, f"{CONSUMER}&zone=hz") as router:
        assert list(router.route((near, far), invocation())) == [near]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"conditions": ["= 1 => zone = x"]}, "cannot read '= 1'"),
        ({"conditions": ["host = 1 => &"]}, "cannot read ''"),
        ({"conditions": ["=> zone = x,,y"]}, "cannot read 'zone = x,,y'"),
        ({"conditions": ["=> port = ~"]}, "has no bound"),
        ({"conditions": [{"to": [{"match": "zone = x", "weight": 0}]}]}, "must be positive"),
        ({"conditions": ["=> zone = x", " "]}, "must not be blank"),
    ],
    ids=[
        "missing-match-key",
        "empty-provider-clause",
        "empty-alternative",
        "unbounded-range",
        "nonpositive-destination-weight",
        "blank-condition",
    ],
)
async def test_condition_router_logs_malformed_rules_and_keeps_the_previous_rule(
    data, message, config_store, provider, invocation, routed, caplog
):
    key = "test.Greeter:1.0:.condition-router"
    a, b = provider("10.0.0.1"), provider("10.0.0.2")
    config_store.put(key, "force: true\nconditions: ['=> host = 10.0.0.1']")

    async with routed(ConditionRouter) as router:
        config_store.put(key, json.dumps(data))
        await anyio.wait_all_tasks_blocked()
        result = router.route((a, b), invocation())

    assert result == [a]
    [record] = caplog.records
    assert (record.name, record.levelno, record.args[0], record.exc_info) == (
        "dubbo.cluster.rule",
        logging.WARNING,
        key,
        None,
    )
    assert re.search(message, str(record.args[1]))


@pytest.mark.parametrize(
    "data",
    [
        {"enabled": False, "conditions": ["=> zone = x"]},
        {"enabled": False, "conditions": ["host = => zone = x"]},
        {"conditions": []},
    ],
    ids=["disabled", "disabled-malformed", "empty"],
)
async def test_disabled_or_empty_condition_rules_leave_all_candidates(
    data, config_store, provider, invocation, routed, caplog
):
    config_store.put("test.Greeter:1.0:.condition-router", json.dumps(data))
    providers = (provider("10.0.0.1"),)

    async with routed(ConditionRouter) as router:
        result = router.route(providers, invocation())

    assert result is providers
    assert caplog.records == []
