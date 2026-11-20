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

import anyio
import attrs
import pytest

from dubbo.cluster.router.tag import TagRouter
from dubbo.constants import FORCE_TAG_KEY, TAG_KEY
from dubbo.url import PROVIDER_URL, URL

pytestmark = pytest.mark.anyio

CONSUMER = "consumer://10.0.0.1/test.Greeter?application=web&version=1.0"


async def test_a_tag_goes_to_its_providers_and_else_to_the_untagged(provider, invocation, routed):
    gray, plain, blue = provider("a", f"{TAG_KEY}=gray"), provider("b"), provider("c", f"{TAG_KEY}=blue")
    providers = (gray, plain, blue)

    async with routed(TagRouter, center=False) as router:
        router.notify(providers)

        assert router.route(providers, invocation(**{TAG_KEY: "gray"})) == [gray]
        assert router.route(providers, invocation()) == [plain]
        assert router.route(providers, invocation(**{TAG_KEY: "red"})) == [plain]
        assert router.route(providers, invocation(**{TAG_KEY: "red", FORCE_TAG_KEY: "true"})) == []
        assert router.route(providers, invocation(**{TAG_KEY: "*"})) is providers

    async with routed(TagRouter, f"{CONSUMER}&{TAG_KEY}=blue", center=False) as router:
        assert router.route(providers, invocation()) == [blue]


async def test_a_tag_routes_to_the_same_sequence_until_the_providers_or_the_rules_change(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1", f"{TAG_KEY}=gray"), provider("10.0.0.2"), provider("10.0.0.3")
    providers = (a, b, c)

    async with routed(TagRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()
        gray = router.route(providers, invocation(**{TAG_KEY: "gray"}))
        again = router.route(providers, invocation(**{TAG_KEY: "gray"}))
        untagged = router.route(providers, invocation())

        config_store.put("greeter.tag-router", "tags: [{name: gray, addresses: ['10.0.0.2']}]")
        await anyio.wait_all_tasks_blocked()
        ruled = router.route(providers, invocation(**{TAG_KEY: "gray"}))
        moved = router.route(list(providers), invocation())

    assert again is gray
    assert (gray, untagged, ruled, moved) == ([a], [b, c], [b], [c])


async def test_a_tag_rule_of_the_provider_application_tags_providers_by_address(
    config_store, provider, invocation, routed
):
    a, b, c = provider("10.0.0.1"), provider("10.0.0.2"), provider("10.0.0.3", port=20881)
    providers = (a, b, c)
    config_store.put(
        "greeter.tag-router",
        "force: false\ntags:\n"
        "  - {name: gray, addresses: ['10.0.0.1:20880']}\n"
        "  - {name: gray|canary, addresses: ['10.0.0.2-3']}\n",
    )

    async with routed(TagRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()

        assert router.route(providers, invocation(**{TAG_KEY: "gray"})) == [a]
        assert router.route(providers, invocation(**{TAG_KEY: "gray|canary|x"})) == [b, c]
        # Providers a rule tags are not untagged.
        assert router.route(providers, invocation()) == []

        config_store.put("greeter.tag-router", None)
        await anyio.wait_all_tasks_blocked()
        assert router.route(providers, invocation()) is providers


async def test_the_tag_rules_of_several_applications_tag_their_own_providers_and_route_together(
    config_store, provider, invocation, routed
):
    a1, a2 = provider("10.0.0.1"), provider("10.0.0.2")
    b1, b2 = provider("10.0.0.3", app="other"), provider("10.0.0.4", app="other")
    providers = (a1, a2, b1, b2)
    # The address of b2 in the rule of greeter tags no provider of other.
    config_store.put("greeter.tag-router", "tags: [{name: gray, addresses: ['10.0.0.1:20880', '10.0.0.4:20880']}]")
    config_store.put(
        "other.tag-router",
        "force: true\ntags: [{name: gray, addresses: ['10.0.0.3']}, {name: blue, addresses: ['10.0.0.9']}]",
    )

    async with routed(TagRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()

        assert router.route(providers, invocation(**{TAG_KEY: "gray"})) == [a1, b1]
        assert router.route(providers, invocation()) == [a2, b2]
        # A tag of a forced rule that tags no provider keeps its calls.
        assert router.route(providers, invocation(**{TAG_KEY: "blue"})) == []


async def test_a_v3_tag_rule_tags_providers_by_parameters_and_a_forced_rule_keeps_its_tag(
    config_store, provider, invocation, routed
):
    a, b = provider("10.0.0.1", "env=gray"), provider("10.0.0.2", "env=prod")
    config_store.put(
        "greeter.tag-router",
        "configVersion: v3.0\nforce: true\ntags:\n"
        "  - {name: gray, match: [{key: env, value: {exact: gray}}]}\n"
        "  - {name: blue, addresses: ['192.168.0.0/16']}\n",
    )

    async with routed(TagRouter) as router:
        router.notify((a, b))
        await anyio.wait_all_tasks_blocked()

        assert router.route((a, b), invocation(**{TAG_KEY: "gray"})) == [a]
        assert router.route((a, b), invocation(**{TAG_KEY: "blue"})) == []
        assert router.route((a, b), invocation()) == [b]


async def test_an_unreadable_rule_is_logged_and_the_one_before_stays(
    config_store, caplog, provider, invocation, routed
):
    a, b = provider("10.0.0.1"), provider("10.0.0.2")
    config_store.put("greeter.tag-router", "tags: [{name: gray, addresses: ['10.0.0.1']}]")

    async with routed(TagRouter) as router:
        router.notify((a, b))
        await anyio.wait_all_tasks_blocked()
        with caplog.at_level(logging.WARNING):
            config_store.put("greeter.tag-router", "tags: [{addresses: ['10.0.0.2']}]")
            await anyio.wait_all_tasks_blocked()

        assert router.route((a, b), invocation(**{TAG_KEY: "gray"})) == [a]
        [record] = caplog.records
        assert (record.name, record.levelno, record.args[0], record.exc_info) == (
            "dubbo.cluster.rule",
            logging.WARNING,
            "greeter.tag-router",
            None,
        )
        assert "needs a name" in str(record.args[1])


async def test_tag_rules_select_the_providers_their_addresses_match(config_store, provider, invocation, routed):
    inside, outside = provider("10.0.9.3"), provider("10.0.9.6")
    config_store.put("greeter.tag-router", "force: true\ntags: [{name: gray, addresses: ['10.0.*.1-5']}]")

    async with routed(TagRouter) as router:
        router.notify((inside, outside))
        await anyio.wait_all_tasks_blocked()

        assert router.route((inside, outside), invocation(**{TAG_KEY: "gray"})) == [inside]


async def test_tag_rules_list_providers_by_exact_addresses_as_by_any_pattern(
    config_store, provider, invocation, routed
):
    providers = (
        provider("10.0.0.1"),
        provider("10.0.0.1", port=20881),
        provider("10.0.0.2"),
        provider("fe80::1"),
        provider("fe80::1", port=20881),
    )
    patterns = ["10.0.0.1", "10.0.0.1:20881", "10.0.0.2:020880", "[fe80::1]:20881", "fe80:0::1", "10.0.0.1-1"]
    tags = ", ".join(f"{{name: t{index}, addresses: ['{pattern}']}}" for index, pattern in enumerate(patterns))
    config_store.put("greeter.tag-router", f"force: true\ntags: [{tags}]")

    async with routed(TagRouter) as router:
        router.notify(providers)
        await anyio.wait_all_tasks_blocked()
        routed_by = [
            list(router.route(providers, invocation(**{TAG_KEY: f"t{index}"}))) for index in range(len(patterns))
        ]

    assert routed_by == [
        [providers[0], providers[1]],
        [providers[1]],
        [],
        [providers[4]],
        [providers[3], providers[4]],
        [providers[0], providers[1]],
    ]


async def test_a_malformed_tag_address_is_logged_and_leaves_the_provider_untagged(
    config_store, provider, invocation, routed, caplog
):
    remote = provider("10.0.0.1", port=1)
    config_store.put("greeter.tag-router", "force: true\ntags: [{name: gray, addresses: ['10.0.*']}]")

    async with routed(TagRouter) as router:
        router.notify((remote,))
        await anyio.wait_all_tasks_blocked()
        selected = router.route((remote,), invocation(**{TAG_KEY: "gray"}))
        assert router.route((remote,), invocation()) == (remote,)

    assert selected == []
    assert [(record.name, record.levelno) for record in caplog.records] == [
        ("dubbo.cluster.router.tag", logging.WARNING)
    ]


@pytest.mark.parametrize("center", [False, True], ids=["by-parameter", "by-rules"])
async def test_a_provider_has_the_tag_it_publishes_whatever_its_calls_set(
    config_store, provider, invocation, routed, center
):
    def calling(published: URL, **parameters: str):
        return attrs.evolve(
            provider("10.0.0.1"),
            url=published.update_parameters(parameters).replace(attributes={PROVIDER_URL: published}),
        )

    plain = calling(URL.parse("tri://10.0.0.1:20880/test.Greeter?remote.application=greeter"), **{TAG_KEY: "blue"})
    blue = calling(URL.parse(f"tri://10.0.0.2:20880/test.Greeter?remote.application=greeter&{TAG_KEY}=blue"))
    if center:
        config_store.put("greeter.tag-router", "tags: [{name: red, addresses: ['10.0.0.9']}]")

    async with routed(TagRouter, center=center) as router:
        router.notify((plain, blue))
        await anyio.wait_all_tasks_blocked()

        assert router.route((plain, blue), invocation(**{TAG_KEY: "blue", FORCE_TAG_KEY: "true"})) == [blue]
        assert router.route((plain, blue), invocation()) == [plain]


async def test_a_v3_tag_rule_matches_the_parameters_a_provider_publishes(config_store, provider, invocation, routed):
    published = URL.parse("tri://10.0.0.1:20880/test.Greeter?remote.application=greeter&application=greeter")
    a = attrs.evolve(
        provider("10.0.0.1"),
        url=published.update_parameters({"application": "web"}).replace(attributes={PROVIDER_URL: published}),
    )
    b = provider("10.0.0.2")
    config_store.put(
        "greeter.tag-router",
        "configVersion: v3.0\ntags: [{name: gray, match: [{key: application, value: {exact: greeter}}]}]\n",
    )

    async with routed(TagRouter) as router:
        router.notify((a, b))
        await anyio.wait_all_tasks_blocked()

        assert router.route((a, b), invocation(**{TAG_KEY: "gray"})) == [a]


def test_a_tag_router_refuses_a_force_of_the_reference_that_is_not_a_boolean():
    with pytest.raises(ValueError, match=FORCE_TAG_KEY):
        TagRouter(URL.parse(f"{CONSUMER}&{FORCE_TAG_KEY}=maybe"))
