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

from contextlib import asynccontextmanager
from importlib.metadata import version

import anyio
import attrs
import pytest

from dubbo.extension import ApplicationScope, extensions
from dubbo.registry import InterfaceRegistry
from dubbo.registry.consumer import Consumer, register_consumer
from dubbo.rpc.definition import Method, Service
from dubbo.url import APPLICATION_SCOPE, PROVIDER_URL, URL
from dubbo.utils import Latest

CONSUMER = Consumer(interface="test.Greeter", group="a", version="1", parameters={"application": "c"})


@pytest.mark.parametrize(
    ("query", "accepted"),
    [
        ("group=a&version=1", True),
        ("group=b&version=1", False),
        ("group=a&version=2", False),
        ("group=a&version=1&category=consumers", False),
        ("group=a&version=1&interface=test.Other", False),
    ],
)
def test_a_consumer_accepts_providers_of_its_service_only(query, accepted):
    url = URL.parse(f"tri://10.0.0.5:50051/test.Greeter?{query}")

    assert (CONSUMER.prepare(url) is not None) is accepted


def test_a_consumer_ignores_providers_of_protocols_not_installed():
    assert CONSUMER.prepare(URL.parse("rest://10.0.0.5:8080/test.Greeter?group=a&version=1")) is None


@pytest.mark.parametrize(
    ("wanted", "group", "accepted"),
    [("*", "x", True), ("a,b", "b", True), ("a,b", "c", False), (None, None, True), (None, "a", False)],
)
def test_a_consumer_group_may_accept_several(wanted, group, accepted):
    consumer = Consumer(interface="test.Greeter", group=wanted, version=None, parameters={})
    query = f"?group={group}" if group else ""

    assert (consumer.prepare(URL.parse(f"tri://h:1/test.Greeter{query}")) is not None) is accepted


def test_the_consumer_timeouts_come_before_those_of_a_provider():
    consumer = Consumer(
        interface="test.Greeter", group=None, version=None, parameters={"timeout": "100", "Greet.timeout": "100"}
    )

    url = consumer.prepare(
        URL.parse("tri://10.0.0.5:1/test.Greeter?methods=Greet,Say&timeout=2000&Greet.timeout=50&Say.timeout=30")
    )

    assert url is not None
    assert url.parameters == {"methods": "Greet,Say", "timeout": "100", "Greet.timeout": "100", "Say.timeout": "30"}


def test_a_provider_url_takes_only_what_providers_publish_for_their_consumers():
    provider = URL.parse(
        "tri://10.0.0.5:50051/test.Greeter?application=p&group=a&version=1&timeout=2000&weight=50&dubbo.tag=gray"
        "&timestamp=7&methods=Greet&Greet.weight=5&Greet.retries=9&zone=x&serialization=hessian2&shutwait=30000"
        "&triple.compressor=gzip"
    )

    url = CONSUMER.prepare(provider)

    assert url == URL.parse(
        "tri://10.0.0.5:50051/test.Greeter?application=c&remote.application=p&group=a&version=1&timeout=2000"
        "&weight=50&dubbo.tag=gray&timestamp=7&methods=Greet&Greet.weight=5&serialization=hessian2"
    )


def test_a_provider_url_takes_the_serialization_of_the_reference_over_that_of_the_provider():
    consumer = attrs.evolve(CONSUMER, parameters={"application": "c", "serialization": "protobuf"})

    url = consumer.prepare(URL.parse("tri://10.0.0.5:1/test.Greeter?group=a&version=1&serialization=hessian2"))

    assert url is not None
    assert url.parameters["serialization"] == "protobuf"


def test_a_provider_url_takes_the_attributes_of_the_reference_and_keeps_what_the_provider_published():
    consumer = attrs.evolve(CONSUMER, attributes={"key": "value"})
    published = URL.parse("tri://10.0.0.5:50051/test.Greeter?group=a&version=1")

    url = consumer.prepare(published)

    assert url is not None
    assert url.attributes == {"key": "value", PROVIDER_URL: published}


def test_a_provider_url_takes_the_tag_of_the_provider_alone():
    consumer = attrs.evolve(CONSUMER, parameters={"application": "c", "dubbo.tag": "gray"})

    untagged = consumer.prepare(URL.parse("tri://10.0.0.5:1/test.Greeter?group=a&version=1"))
    tagged = consumer.prepare(URL.parse("tri://10.0.0.5:1/test.Greeter?group=a&version=1&dubbo.tag=blue"))

    assert untagged is not None
    assert "dubbo.tag" not in untagged.parameters
    assert tagged is not None
    assert tagged.parameters["dubbo.tag"] == "blue"


def test_a_provider_url_that_lists_no_methods_keeps_what_it_publishes_for_each_method():
    url = CONSUMER.prepare(
        URL.parse("tri://10.0.0.5:1/test.Greeter?group=a&version=1&Greet.timeout=50&Greet.retries=9&.weight=1")
    )

    assert url is not None
    assert url.parameters == {"application": "c", "group": "a", "version": "1", "Greet.timeout": "50"}


@pytest.mark.anyio
async def test_a_watch_keeps_the_url_of_a_provider_that_does_not_change():
    unchanged = URL.parse("tri://10.0.0.5:1/test.Greeter?group=a&version=1")
    snapshots = Latest()

    @asynccontextmanager
    async def subscription():
        yield aiter(snapshots)

    snapshots.publish([unchanged])
    with anyio.fail_after(5):
        async with CONSUMER.watch(subscription(), URL.parse("tri://10.0.0.1/test.Greeter")) as urls:
            [first] = await anext(urls)
            snapshots.publish([unchanged, URL.parse("tri://10.0.0.6:1/test.Greeter?group=a&version=1")])
            kept, _ = await anext(urls)

    assert kept is first


class _Registry(InterfaceRegistry):
    def __init__(self, url, registered, removed):
        super().__init__(url)
        self.registered, self.removed = registered, removed

    @asynccontextmanager
    async def register(self, url):
        self.registered.append(url)
        try:
            yield
        finally:
            self.removed.append(url)

    async def aclose(self):
        pass

    async def __aenter__(self):
        return self


@pytest.mark.parametrize(
    ("generic", "extra"),
    [(None, {"methods": "Greet"}), ("protobuf-json", {"generic": "protobuf-json"})],
    ids=["contract", "generic"],
)
@pytest.mark.anyio
async def test_consumer_registration_publishes_its_generic_mode_in_place_of_methods(
    isolated_extensions, monkeypatch, generic, extra
):
    registered, removed = [], []

    monkeypatch.setattr("time.time_ns", lambda: 1700000000000000000)
    extensions.register(InterfaceRegistry, "memory", lambda url: _Registry(url, registered, removed))
    service = Service(interface="test.Greeter", methods=[Method(name="Greet", request=(), response=None)])
    reference = URL.parse("consumer://10.0.0.9/test.Greeter?application=c&group=a&timeout=1000")

    async with ApplicationScope() as scope:
        registry = URL.parse("memory://registry?register-mode=interface").replace(attributes={APPLICATION_SCOPE: scope})
        async with register_consumer(reference, service, [registry], generic=generic):
            assert registered == [
                URL(
                    protocol="consumer",
                    host="10.0.0.9",
                    path="test.Greeter",
                    parameters={
                        "application": "c",
                        "group": "a",
                        "side": "consumer",
                        "category": "consumers",
                        "check": "false",
                        "interface": "test.Greeter",
                        "dubbo": "2.0.2",
                        "release": version("apache-dubbo"),
                        "timestamp": "1700000000000",
                        **extra,
                    },
                )
            ]
            assert removed == []

    assert removed == registered
