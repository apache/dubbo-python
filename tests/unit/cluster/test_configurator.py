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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest

from dubbo.cluster.configurator import Overrides
from dubbo.extension import ApplicationScope
from dubbo.registry.consumer import Consumer
from dubbo.url import APPLICATION_SCOPE, CONFIG_CENTER_URL, URL

pytestmark = pytest.mark.anyio

REFERENCE = "consumer://10.0.0.9/test.Greeter?application=web&version=1.0"
A = URL.parse("tri://10.0.0.1:20880/test.Greeter?application=web&version=1.0&timeout=1000")
B = URL.parse("tri://10.0.0.2:20880/test.Greeter?application=web&version=1.0&timeout=1000")


@asynccontextmanager
async def _reference() -> AsyncIterator[URL]:
    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            center = URL(protocol="memory", attributes={APPLICATION_SCOPE: scope})
            yield URL.parse(REFERENCE).replace(attributes={APPLICATION_SCOPE: scope, CONFIG_CENTER_URL: center})


_MATCH = {
    "address": "{cird: '10.0.0.0/24'}",
    "providerAddress": "{wildcard: '10.0.0.2*'}",
    "service": "{oneof: [{exact: 'test.Greeter:1.0'}]}",
    "application": "{oneof: [{prefix: 'we'}]}",
    "param": "[{key: timeout, value: {exact: '1000'}}]",
}


def _timeouts(urls: list[URL]) -> list[str | None]:
    return [url.parameters.get("timeout") for url in urls]


async def test_overrides_of_the_service_win_over_those_of_the_application_and_specific_hosts_over_any(config_store):
    config_store.put(
        "web.configurators",
        "scope: application\nkey: web\nconfigs:\n"
        "  - {side: consumer, addresses: ['10.0.0.9'], parameters: {timeout: 3000}}\n"
        "  - {side: consumer, addresses: ['0.0.0.0'], parameters: {timeout: 2000, retries: 5}}\n"
        "  - {side: provider, parameters: {weight: 1}}\n",
    )
    config_store.put(
        "test.Greeter:1.0:.configurators",
        "scope: service\nkey: test.Greeter:1.0\nconfigs:\n"
        "  - {side: consumer, providerAddresses: ['10.0.0.2:20880'], parameters: {timeout: 4000}}\n",
    )

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        a, b = overrides.configure([A, B])

    assert (a.parameters["timeout"], a.parameters["retries"], b.parameters["timeout"]) == ("3000", "5", "4000")
    assert "weight" not in a.parameters


async def test_overrides_for_other_consumers_services_or_applications_change_nothing(config_store):
    config_store.put(
        "web.configurators",
        "scope: application\nkey: web\nconfigs:\n"
        "  - {side: consumer, addresses: ['10.0.0.8'], parameters: {timeout: 1}}\n"
        "  - {side: consumer, services: [test.Other], parameters: {timeout: 2}}\n",
    )
    config_store.put(
        "test.Greeter:1.0:.configurators",
        "scope: service\nkey: test.Greeter:1.0\nenabled: true\nconfigs:\n"
        "  - {side: consumer, applications: [mobile], parameters: {timeout: 3}}\n",
    )

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        assert _timeouts(overrides.configure([A, B])) == ["1000", "1000"]


async def test_a_reference_calls_its_providers_again_with_the_overrides_that_change(config_store):
    @asynccontextmanager
    async def fixed() -> AsyncIterator[AsyncIterator[list[URL]]]:
        async def snapshots() -> AsyncIterator[list[URL]]:
            yield [A]
            await anyio.sleep_forever()

        yield snapshots()

    consumer = Consumer(interface="test.Greeter", group=None, version="1.0", parameters={"application": "web"})
    async with _reference() as url, consumer.watch(fixed(), url) as watched:
        assert _timeouts(await anext(watched)) == ["1000"]

        config_store.put(
            "web.configurators", "scope: application\nkey: web\nconfigs: [{side: consumer, parameters: {timeout: 9}}]"
        )
        with anyio.fail_after(5):
            assert _timeouts(await anext(watched)) == ["9"]


def _match_rule(match: dict[str, str]) -> str:
    return (
        "configVersion: v3.0\nscope: service\nkey: test.Greeter:1.0\nconfigs:\n"
        "  - side: consumer\n    parameters: {timeout: 5}\n    match:\n"
        + "".join(f"      {name}: {value}\n" for name, value in match.items())
    )


async def test_a_config_applies_to_the_urls_its_match_takes_in(config_store):
    config_store.put("test.Greeter:1.0:.configurators", _match_rule(_MATCH))

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        assert _timeouts(overrides.configure([A, B])) == ["1000", "5"]


@pytest.mark.parametrize(
    "mismatch",
    [
        {"address": "{exact: '10.0.0.8'}"},
        {"service": "{oneof: [{exact: test.Other}]}"},
        {"app": "{oneof: [{exact: mobile}]}"},
        {"param": "[{key: timeout, value: {exact: '9'}}]"},
    ],
    ids=["different-consumer-address", "different-service", "different-application", "different-parameter"],
)
async def test_a_config_leaves_out_the_urls_one_part_of_its_match_does_not_take_in(config_store, mismatch):
    config_store.put("test.Greeter:1.0:.configurators", _match_rule({**_MATCH, **mismatch}))

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        assert _timeouts(overrides.configure([A, B])) == ["1000", "1000"]


async def test_an_empty_match_takes_in_every_url(config_store):
    config_store.put(
        "web.configurators",
        "configVersion: v3.0\nscope: application\nkey: web\nconfigs:\n"
        "  - {side: consumer, match: {}, parameters: {timeout: 7}}\n",
    )

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        assert _timeouts(overrides.configure([A, B])) == ["7", "7"]


async def test_overrides_disable_providers_and_enable_those_registered_disabled(config_store):
    off = URL.parse("tri://10.0.0.3:20880/test.Greeter?version=1.0&disabled=true")
    plain = URL.parse("tri://10.0.0.4:20880/test.Greeter?version=1.0&disabled=false&enabled=false")

    @asynccontextmanager
    async def fixed() -> AsyncIterator[AsyncIterator[list[URL]]]:
        async def snapshots() -> AsyncIterator[list[URL]]:
            yield [A, B, off, plain]
            await anyio.sleep_forever()

        yield snapshots()

    consumer = Consumer(interface="test.Greeter", group=None, version="1.0", parameters={"application": "web"})
    async with _reference() as url, consumer.watch(fixed(), url) as watched:
        # disabled, when set, wins over enabled.
        assert [found.host for found in await anext(watched)] == ["10.0.0.1", "10.0.0.2", "10.0.0.4"]

        config_store.put(
            "web.configurators",
            "scope: application\nkey: web\nconfigs:\n"
            "  - {side: consumer, providerAddresses: ['10.0.0.1:20880'], parameters: {disabled: true}}\n"
            "  - {side: consumer, providerAddresses: ['10.0.0.3'], parameters: {disabled: false}}\n",
        )
        with anyio.fail_after(5):
            assert [found.host for found in await anext(watched)] == ["10.0.0.2", "10.0.0.3", "10.0.0.4"]


@pytest.mark.parametrize(
    ("address", "timeouts"),
    [("[::1]:20880", ["9", "1000"]), ("[::1]", ["9", "9"]), ("0.0.0.0:20880", ["9", "1000"]), ("*", ["9", "9"])],
    ids=["ipv6-port", "ipv6", "any-host", "any"],
)
async def test_overrides_apply_to_the_provider_addresses_they_list(address, timeouts, config_store):
    v6 = URL.parse("tri://[::1]:20880/test.Greeter?application=web&version=1.0&timeout=1000")
    config_store.put(
        "web.configurators",
        "scope: application\nkey: web\n"
        f"configs: [{{side: consumer, providerAddresses: ['{address}'], parameters: {{timeout: 9}}}}]",
    )

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        configured = overrides.configure([v6, v6.replace(port=20881)])

    assert _timeouts(configured) == timeouts


async def test_provider_overrides_apply_to_the_url_a_provider_registers_at_its_host(config_store):
    config_store.put(
        "web.configurators",
        "scope: application\nkey: web\nconfigs:\n"
        "  - {side: provider, addresses: ['10.0.0.1'], parameters: {weight: 50}}\n"
        "  - {side: consumer, parameters: {timeout: 1}}\n",
    )

    async with _reference() as reference:
        for provider, weight in ((A, "50"), (B, None)):
            url = provider.replace(attributes=reference.attributes)
            async with Overrides(url, "provider") as overrides:
                (configured,) = overrides.configure([url])
            assert (configured.parameters.get("weight"), configured.parameters["timeout"]) == (weight, "1000")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"configs": []}, "needs a key"),
        ({"key": "web", "configs": [{"side": "consumer"}]}, "needs parameters"),
        (
            {"key": "web", "configs": [{"side": "consumer", "match": {"address": "*"}, "parameters": {"a": 1}}]},
            "address",
        ),
        (
            {
                "key": "web",
                "configs": [{"side": "consumer", "match": {"param": [{"value": {}}]}, "parameters": {"a": 1}}],
            },
            "needs a key",
        ),
    ],
    ids=["missing-rule-key", "missing-parameters", "nonmapping-address-match", "missing-parameter-match-key"],
)
async def test_overrides_log_malformed_rules_and_keep_the_previous_parameters(data, message, config_store, caplog):
    config_store.put(
        "web.configurators", "scope: application\nkey: web\nconfigs: [{side: consumer, parameters: {timeout: 7}}]"
    )

    async with _reference() as url, Overrides(url, "consumer") as overrides:
        config_store.put("web.configurators", json.dumps(data))
        await anyio.wait_all_tasks_blocked()
        configured = overrides.configure([A, B])

    assert _timeouts(configured) == ["7", "7"]
    [record] = caplog.records
    assert (record.name, record.levelno, record.args[0], record.exc_info) == (
        "dubbo.cluster.rule",
        logging.WARNING,
        "web.configurators",
        None,
    )
    assert re.search(message, str(record.args[1]))


async def test_overrides_log_an_unparsable_rule_without_its_text(config_store, caplog):
    async with _reference() as url, Overrides(url, "consumer") as overrides:
        config_store.put("web.configurators", "key: web\nconfigs: [{parameters: {token: rv08demo}")
        await anyio.wait_all_tasks_blocked()
        configured = overrides.configure([A])

    assert configured == [A]
    assert [(record.levelno, record.exc_info) for record in caplog.records] == [(logging.WARNING, None)]
    assert "rv08demo" not in caplog.text


@pytest.mark.parametrize(
    ("side", "data"),
    [
        ("consumer", {"enabled": False, "configs": [{"side": "consumer", "parameters": {"timeout": 1}}]}),
        ("consumer", {"configs": [{"side": "provider", "parameters": {"weight": 1}}]}),
        ("provider", {"configs": [{"side": "consumer", "parameters": {"timeout": 1}}]}),
    ],
    ids=["disabled", "provider-rule-at-consumer", "consumer-rule-at-provider"],
)
async def test_disabled_rules_and_rules_for_the_other_side_leave_urls_unchanged(side, data, config_store):
    config_store.put("web.configurators", json.dumps({"scope": "application", "key": "web", **data}))

    async with _reference() as url, Overrides(url, side) as overrides:
        configured = overrides.configure([A, B])

    assert configured == [A, B]
