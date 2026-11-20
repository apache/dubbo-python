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

import itertools
import json
import logging
import socket
import typing
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl, unquote_plus, urlencode

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import Dubbo, RpcError, Status
from dubbo.config import (
    ApplicationConfig,
    ConfigError,
    ConsumerConfig,
    MetadataReportConfig,
    MetadataType,
    MethodConfig,
    ProtocolConfig,
    ProviderConfig,
    ReferenceConfig,
    RegistryMode,
    ServiceConfig,
    ShutdownConfig,
    TLSConfig,
    TripleConfig,
)
from dubbo.constants import DEFAULT_ROUTERS
from dubbo.extension import ExtensionError
from dubbo.metadata.service.server import MetadataStore
from dubbo.protocol.served import ServedExporter
from dubbo.protocol.triple import TripleProtocol
from dubbo.protocol.triple.invoker import TripleInvoker
from dubbo.registry.zookeeper import ZookeeperInstanceRegistry
from dubbo.registry.zookeeper.interface import ZookeeperInterfaceRegistry, _parse_full_string
from dubbo.transport.h2.aio import AioH2Client
from dubbo.url import URL

pytestmark = pytest.mark.anyio
# The routers of references that consumer_updates follows.
_UPDATES = (*DEFAULT_ROUTERS, "updates")


async def test_a_consumer_calls_a_provider_found_by_interface(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

        async with zk(registry_address) as client:
            root = "/" + URL.parse(registry_address).parameters["group"]
            providers = await client.children(f"{root}/test.registry.Greeter/providers")
            consumers = await client.children(f"{root}/test.registry.Greeter/consumers")
            assert await client.children(f"{root}/test.registry.Greeter") == ["consumers", "providers"]

    [node] = providers
    url = _parse_full_string(unquote_plus(node))
    assert (url.protocol, url.host, url.path) == ("tri", "127.0.0.1", "test.registry.Greeter")
    assert {key: url.parameters[key] for key in ("application", "interface", "methods", "side", "dubbo")} == {
        "application": "greeter-app",
        "interface": "test.registry.Greeter",
        "methods": "Greet",
        "side": "provider",
        "dubbo": "2.0.2",
    }
    [node] = consumers
    url = _parse_full_string(unquote_plus(node))
    assert (url.protocol, url.host, url.parameters["category"], url.parameters["side"]) == (
        "consumer",
        "127.0.0.1",
        "consumers",
        "consumer",
    )


async def test_a_provider_whose_filters_cannot_load_is_left_out_and_its_invoker_closed(
    registry_address, monkeypatch, greeter_contract, greeter_impl_type, consumer, provider
):
    closed = anyio.Event()
    aclose = TripleInvoker.aclose

    async def recording(invoker):
        await aclose(invoker)
        closed.set()

    monkeypatch.setattr(TripleInvoker, "aclose", recording)
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE, check=False, attempt_filters=("missing",))
    greeter = caller.refer(greeter_contract)

    with anyio.fail_after(5):
        async with app, caller:
            await closed.wait()
            with pytest.raises(RpcError, match="UNAVAILABLE"):
                await greeter.greet(StringValue(value="b"))


async def test_a_simplified_registry_gets_only_what_consumers_need(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    address = f"{registry_address}&simplified=true&extra-keys=timestamp"
    app = provider(address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(address, RegistryMode.INTERFACE)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

        async with zk(registry_address) as client:
            root = "/" + URL.parse(registry_address).parameters["group"]
            [provider_node] = await client.children(f"{root}/test.registry.Greeter/providers")
            [consumer_node] = await client.children(f"{root}/test.registry.Greeter/consumers")

    url = _parse_full_string(unquote_plus(provider_node))
    assert set(url.parameters) == {"application", "dubbo", "release", "side", "timestamp"}
    url = _parse_full_string(unquote_plus(consumer_node))
    assert set(url.parameters) == {"application", "dubbo", "release", "category", "check"}


async def test_the_tags_of_services_and_references_are_registered(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    app = provider(registry_address, RegistryMode.INTERFACE, settings=ProviderConfig(tag="gray"))
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE, tag="blue")
    caller.refer(greeter_contract)

    async with app, caller, zk(registry_address) as client:
        root = "/" + URL.parse(registry_address).parameters["group"]
        [provider_node] = await client.children(f"{root}/test.registry.Greeter/providers")
        [consumer_node] = await client.children(f"{root}/test.registry.Greeter/consumers")

    assert _parse_full_string(unquote_plus(provider_node)).parameters["dubbo.tag"] == "gray"
    assert _parse_full_string(unquote_plus(consumer_node)).parameters["dubbo.tag"] == "blue"


async def test_a_reference_of_a_forced_tag_calls_only_the_providers_found_with_that_tag(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider
):
    plain = provider(registry_address, RegistryMode.INTERFACE)
    plain.export(greeter_impl_type("plain"))
    blue = provider(registry_address, RegistryMode.INTERFACE, settings=ProviderConfig(tag="blue"))
    blue.export(greeter_impl_type("blue"))
    tagged = consumer(
        registry_address,
        RegistryMode.INTERFACE,
        tag="blue",
        loadbalance="roundrobin",
        parameters={"dubbo.force.tag": "true"},
    )
    untagged = consumer(registry_address, RegistryMode.INTERFACE)
    tagged_greeter, untagged_greeter = tagged.refer(greeter_contract), untagged.refer(greeter_contract)

    async with plain, blue, tagged, untagged:
        answers = [(await tagged_greeter.greet(StringValue(value="b"))).value for _ in range(4)]
        assert (await untagged_greeter.greet(StringValue(value="b"))).value == "plain: hello b"

    assert answers == ["blue: hello b"] * 4


async def test_an_application_that_does_not_register_leaves_the_registry_alone(
    registry_address, greeter_contract, greeter_impl_type, registry_config, zk
):
    registries = {"zk": registry_config(registry_address, mode=RegistryMode.INTERFACE, register=False)}
    app = Dubbo(
        application=ApplicationConfig(name="greeter-app"),
        registries=registries,
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0)},
        env_prefix=None,
    )
    app.export(greeter_impl_type())
    caller = Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries=registries,
        consumer=ConsumerConfig(references={"test.registry.Greeter": ReferenceConfig(check=False)}),
        env_prefix=None,
    )
    caller.refer(greeter_contract)

    async with app, caller, zk(registry_address) as client:
        root = "/" + URL.parse(registry_address).parameters["group"]
        assert await client.children(f"{root}/test.registry.Greeter") == []


async def test_startup_fails_when_a_reference_subscribes_to_none_of_its_registries(
    registry_address, greeter_contract, registry_config
):
    caller = Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries={"zk": registry_config(registry_address, subscribe=False)},
        env_prefix=None,
    )
    caller.refer(greeter_contract)

    with pytest.raises(ConfigError, match="subscribes to none of its registries"):
        async with caller:
            pass


async def test_a_reference_calls_the_providers_it_names_besides_those_of_its_registries(
    registry_address, exported_urls, greeter_contract, greeter_impl_type, consumer, provider
):
    registered = provider(registry_address, RegistryMode.INTERFACE)
    registered.export(greeter_impl_type("registered"))
    named = Dubbo(protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0)}, env_prefix=None)
    named.export(greeter_impl_type("named"))

    async with registered, named:
        url = exported_urls[-1]
        caller = consumer(
            registry_address, RegistryMode.INTERFACE, urls=(str(url),), registries=("zk",), loadbalance="roundrobin"
        )
        greeter = caller.refer(greeter_contract)
        async with caller:
            answers = [(await greeter.greet(StringValue(value="b"))).value for _ in range(2)]

    assert set(answers) == {"registered: hello b", "named: hello b"}


async def test_providers_leave_the_registry_when_they_stop(
    registry_address, consumer_updates, greeter_contract, greeter_impl_type, consumer, provider
):
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE, routers=_UPDATES, check=False)
    greeter = caller.refer(greeter_contract)

    async with caller:
        since = len(consumer_updates.snapshots)
        async with app:
            await consumer_updates.wait_for(bool, since=since)
            assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
            since = len(consumer_updates.snapshots)

        await consumer_updates.wait_for(lambda urls: not urls, since=since)
        with pytest.raises(RpcError, match="UNAVAILABLE"):
            await greeter.greet(StringValue(value="b"))


async def test_a_stopping_provider_announces_it_then_waits_after_leaving_the_registry(
    registry_address, monkeypatch, greeter_impl_type, provider
):
    events = []
    announce, register, unexport = (
        TripleProtocol.announce_shutdown,
        ZookeeperInterfaceRegistry.register,
        ServedExporter.aclose,
    )

    def announce_shutdown(protocol):
        events.append(("announce", anyio.current_time()))
        announce(protocol)

    @asynccontextmanager
    async def registered(registry, url):
        async with register(registry, url):
            yield
        events.append(("unregister", anyio.current_time()))

    async def close_exporter(exporter):
        events.append(("unexport", anyio.current_time()))
        await unexport(exporter)

    monkeypatch.setattr(TripleProtocol, "announce_shutdown", announce_shutdown)
    monkeypatch.setattr(ZookeeperInterfaceRegistry, "register", registered)
    monkeypatch.setattr(ServedExporter, "aclose", close_exporter)
    app = provider(registry_address, RegistryMode.INTERFACE, shutdown=ShutdownConfig(unregister_wait=0.05))
    app.export(greeter_impl_type())

    with anyio.fail_after(5):
        async with app:
            pass

    assert [name for name, _ in events] == ["announce", "unregister", "unexport"]
    # To the nanosecond: exactly the wait on the virtual clock, at least it against a real ZooKeeper.
    assert round(events[2][1] - events[1][1], 9) >= 0.05


@pytest.mark.parametrize(
    ("timeout", "methods", "registered"),
    [
        (0.05, {}, ("50", None)),
        (5, {"Greet": MethodConfig(timeout=0.05)}, ("5000", "50")),
    ],
    ids=["service-timeout", "method-timeout"],
)
async def test_a_consumer_takes_the_provider_timeout_and_its_identity(
    registry_address, timeout, methods, registered, greeter_contract, consumer, provider, zk
):
    release = anyio.Event()
    settings = ServiceConfig(group="g", version="1", timeout=timeout, methods=methods)

    class Slow(greeter_contract):
        async def greet(self, request):
            await release.wait()
            return request

    app = provider(
        registry_address, RegistryMode.INTERFACE, settings=ProviderConfig(services={"test.registry.Greeter": settings})
    )
    app.export(Slow())
    caller = consumer(registry_address, RegistryMode.INTERFACE, group="*", version="1", retries=0)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            [node] = await client.children(f"{root}/test.registry.Greeter/providers")
        with anyio.fail_after(5), pytest.raises(RpcError, match="DEADLINE_EXCEEDED"):
            await greeter.greet(StringValue(value="b"))
        release.set()

    parameters = _parse_full_string(unquote_plus(node)).parameters
    assert (parameters["group"], parameters["version"]) == ("g", "1")
    assert (parameters["timeout"], parameters.get("Greet.timeout")) == registered


@pytest.mark.parametrize("mode", [RegistryMode.INTERFACE, RegistryMode.INSTANCE], ids=["interface", "instance"])
async def test_consumers_attach_the_token_a_provider_registers_and_hear_what_it_deprecates(
    registry_address, mode, caplog, exported_urls, greeter_contract, greeter_impl_type, consumer, provider
):
    service = ServiceConfig(token=True, methods={"Greet": MethodConfig(deprecated=True)})
    app = provider(registry_address, mode, settings=ProviderConfig(services={"test.registry.Greeter": service}))
    app.export(greeter_impl_type())
    caller = consumer(registry_address, mode)
    greeter = caller.refer(greeter_contract)

    with caplog.at_level(logging.WARNING, logger="dubbo.filter.deprecated"):
        async with app, caller:
            url = next(url for url in exported_urls if url.path == "test.registry.Greeter")
            direct = Dubbo(env_prefix=None)
            stranger = direct.refer(greeter_contract, url=str(url.replace(parameters={})))
            async with direct:
                assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
                assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
                with pytest.raises(RpcError, match="PERMISSION_DENIED"):
                    await stranger.greet(StringValue(value="b"))

    assert [record.getMessage() for record in caplog.records] == [
        f"Calling test.registry.Greeter.Greet, which its provider at 127.0.0.1:{url.port} deprecates"
    ]


async def test_providers_that_leave_give_their_connections_back(
    registry_address, monkeypatch, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    closed = anyio.Event()
    addresses = []
    close = AioH2Client.aclose

    async def recording(client):
        await close(client)
        addresses.append((client.url.host, client.url.port))
        closed.set()

    monkeypatch.setattr(AioH2Client, "aclose", recording)
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            parent = f"{root}/test.registry.Greeter/providers"
            [node] = await client.children(parent)
            await client.delete(f"{parent}/{node}")

        with anyio.fail_after(5):
            await closed.wait()
        url = _parse_full_string(unquote_plus(node))
        assert addresses == [(url.host, url.port)]


async def test_a_call_running_when_its_provider_stops_still_completes(
    registry_address, consumer_updates, monkeypatch, greeter_contract, consumer, provider, zk
):
    started, release, ready, stop, closing = anyio.Event(), anyio.Event(), anyio.Event(), anyio.Event(), anyio.Event()
    results = []
    close = ServedExporter.aclose

    async def observe(exporter):
        closing.set()
        await close(exporter)

    monkeypatch.setattr(ServedExporter, "aclose", observe)

    class Held(greeter_contract):
        async def greet(self, request):
            started.set()
            await release.wait()
            return StringValue(value=f"held {request.value}")

    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(Held())
    caller = consumer(registry_address, RegistryMode.INTERFACE, routers=_UPDATES, check=False, timeout=5.0)
    greeter = caller.refer(greeter_contract)

    async def serve():
        async with app:
            ready.set()
            await stop.wait()

    async def call():
        results.append(await greeter.greet(StringValue(value="hold")))

    with anyio.fail_after(5):
        async with caller, anyio.create_task_group() as tasks:
            since = len(consumer_updates.snapshots)
            tasks.start_soon(serve)
            await ready.wait()
            await consumer_updates.wait_for(bool, since=since)
            tasks.start_soon(call)
            await started.wait()
            root = "/" + URL.parse(registry_address).parameters["group"]
            async with (
                zk(registry_address) as client,
                client.watch_children(f"{root}/test.registry.Greeter/providers") as nodes,
            ):
                assert await anext(nodes)
                stop.set()
                await _until(nodes, lambda children: children == [])
                await closing.wait()
                release.set()

    assert results == [StringValue(value="held hold")]


# Windows refuses the connection after its own retries, in real time.
@pytest.mark.real_clock
async def test_a_cancelled_application_still_stops_serving_and_leaves_the_registry(
    registry_address, greeter_impl_type, provider, zk
):
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    parent = "/" + URL.parse(registry_address).parameters["group"] + "/test.registry.Greeter/providers"

    with anyio.CancelScope() as cancelled:
        async with app:
            async with zk(registry_address) as client:
                [node] = await client.children(parent)
            address = _parse_full_string(unquote_plus(node))
            cancelled.cancel()
            await anyio.sleep_forever()

    with pytest.raises(OSError, match="connection attempts failed"):
        async with await anyio.connect_tcp(address.host, address.port):
            pass
    async with zk(registry_address) as client:
        assert await client.children(parent) == []


async def test_a_protocol_first_used_after_start_closes_with_the_application(
    registry_address, monkeypatch, consumer_updates, greeter_contract, greeter_impl_type, consumer, provider
):
    opened, closed = set(), set()
    init, close = TripleProtocol.__init__, TripleProtocol.aclose

    def recording_init(protocol, **kwargs):
        opened.add(id(protocol))
        init(protocol, **kwargs)

    async def recording_close(protocol):
        await close(protocol)
        closed.add(id(protocol))

    monkeypatch.setattr(TripleProtocol, "__init__", recording_init)
    monkeypatch.setattr(TripleProtocol, "aclose", recording_close)
    caller = consumer(registry_address, RegistryMode.INTERFACE, routers=_UPDATES, check=False)
    greeter = caller.refer(greeter_contract)
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())

    async with caller:
        assert opened == set()
        since = len(consumer_updates.snapshots)
        async with app:
            await consumer_updates.wait_for(bool, since=since)
            assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

    assert len(opened) == 2
    assert closed == opened


@pytest.mark.parametrize("mode", [RegistryMode.INTERFACE, RegistryMode.INSTANCE], ids=["interface", "instance"])
async def test_the_override_rules_of_providers_change_what_they_register(
    registry_address, mode, greeter_impl_type, config_center, provider, zk
):
    root = "/" + URL.parse(registry_address).parameters["group"]
    rule = f"{root}/config/dubbo/greeter-app.configurators"
    app = provider(
        registry_address, mode, config_center=config_center(registry_address), metadata_type=MetadataType.REMOTE
    )
    app.export(greeter_impl_type())

    async with app, zk(registry_address) as client, _registered_weights(client, root, mode) as weights:
        assert await anext(weights) is None
        await client.set(
            rule,
            b"scope: application\nkey: greeter-app\nconfigs:\n  - {side: provider, addresses: ['127.0.0.1'], parameters: {weight: 50}}\n  - {side: provider, addresses: ['10.9.9.9'], parameters: {weight: 1}}\n  - {side: consumer, parameters: {weight: 2}}\n",
        )
        assert await _until(weights, lambda value: value == "50") == "50"
        await client.delete(rule)
        assert await _until(weights, lambda value: value is None) is None


@pytest.mark.parametrize("mode", [RegistryMode.INTERFACE, RegistryMode.INSTANCE], ids=["interface", "instance"])
@pytest.mark.parametrize("side", ["provider", "consumer"])
async def test_calls_keep_succeeding_while_override_rules_swap_the_weights_of_providers(
    registry_address,
    mode,
    side,
    greeter_contract,
    greeter_impl_type,
    config_center,
    registry_config,
    consumer_updates,
    zk,
):
    # A rule for the providers belongs to their application, one for consumers to that of the consumer.
    owner = "greeter-app" if side == "provider" else "caller-app"
    rule = "/" + URL.parse(registry_address).parameters["group"] + f"/config/dubbo/{owner}.configurators"
    ports = _free_ports(4)
    apps = [
        Dubbo(
            application=ApplicationConfig(name="greeter-app"),
            registries={"zk": registry_config(registry_address, mode=mode)},
            protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=port)},
            config_center=config_center(registry_address),
            shutdown=ShutdownConfig(unregister_wait=0),
            env_prefix=None,
        )
        for port in ports
    ]
    for app in apps:
        app.export(greeter_impl_type())
    caller = Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries={"zk": registry_config(registry_address, mode=mode)},
        config_center=config_center(registry_address),
        consumer=ConsumerConfig(references={"test.registry.Greeter": ReferenceConfig(routers=_UPDATES, check=False)}),
        env_prefix=None,
    )
    greeter = caller.refer(greeter_contract)
    stop = anyio.Event()
    calls, errors = [0], []

    async def call():
        while not stop.is_set():
            try:
                await greeter.greet(StringValue(value="b"))
            except RpcError as error:
                errors.append(error)
            calls[0] += 1

    def weights(urls):
        return {url.port: url.parameters.get("weight") for url in urls}

    with anyio.fail_after(30):
        async with AsyncExitStack() as stack:
            for app in apps:
                await stack.enter_async_context(app)
            await stack.enter_async_context(caller)
            client = await stack.enter_async_context(zk(registry_address))
            await consumer_updates.wait_for(lambda urls: len(urls) == len(ports))
            since = len(consumer_updates.snapshots)
            async with anyio.create_task_group() as tasks:
                for _ in range(16):
                    tasks.start_soon(call)
                for idle in (ports[0::2], ports[1::2]) * 4:
                    changed = len(consumer_updates.snapshots)
                    addresses = ", ".join(f"'127.0.0.1:{port}'" for port in idle)
                    await client.set(
                        rule,
                        f"scope: application\nkey: {owner}\nconfigs: [{{side: {side}, providerAddresses: [{addresses}], parameters: {{weight: 0}}}}]\n".encode(),
                    )
                    expected = {port: "0" if port in idle else None for port in ports}
                    await consumer_updates.wait_for(
                        lambda urls, expected=expected: weights(urls) == expected, since=changed
                    )
                    # Calls go on under the new weights before they swap again.
                    until = calls[0] + 64
                    while calls[0] < until:
                        await anyio.sleep(0)
                stop.set()
            seen = consumer_updates.snapshots[since:]

    assert [len(urls) for urls in seen if len(urls) != len(ports)] == []
    assert calls[0] > 0
    assert errors == []


def _free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for each in sockets:
            each.bind(("127.0.0.1", 0))
        return [each.getsockname()[1] for each in sockets]
    finally:
        for each in sockets:
            each.close()


async def test_the_override_rules_of_providers_change_the_filters_they_serve_through(
    registry_address, caplog, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    root = "/" + URL.parse(registry_address).parameters["group"]
    rule = f"{root}/config/dubbo/greeter-app.configurators"
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INTERFACE, retries=0)
    greeter = caller.refer(greeter_contract)

    async with (
        app,
        caller,
        zk(registry_address) as client,
        client.watch_children(f"{root}/test.registry.Greeter/providers") as nodes,
    ):

        async def registered_tps(value):
            return await _until(
                nodes,
                lambda values: (
                    len(values) == 1 and _parse_full_string(unquote_plus(values[0])).parameters.get("tps") == value
                ),
            )

        async def configure(parameters):
            await client.set(rule, b"scope: application\nkey: greeter-app\nconfigs:\n" + parameters)

        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
        await configure(b"  - {side: provider, parameters: {tps: 1, tps.interval: 60000}}\n")
        await registered_tps("1")
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
        with pytest.raises(RpcError, match="UNAVAILABLE"):
            await greeter.greet(StringValue(value="b"))

        await client.delete(rule)
        await registered_tps(None)
        assert [await greeter.greet(StringValue(value="b")) for _ in range(2)] == [StringValue(value="a: hello b")] * 2

        with caplog.at_level(logging.WARNING, logger="dubbo.application"):
            await configure(b"  - {side: provider, parameters: {tps: many}}\n")
            await registered_tps("many")

        assert any("Cannot apply the override rules" in record.getMessage() for record in caplog.records)
        assert [await greeter.greet(StringValue(value="b")) for _ in range(2)] == [StringValue(value="a: hello b")] * 2


async def test_local_metadata_serves_only_the_revision_the_instance_registers(
    registry_address, greeter_impl_type, config_center, provider, zk
):
    from dubbo.metadata.service.v2 import MetadataRequest, MetadataServiceV2

    root = "/" + URL.parse(registry_address).parameters["group"]
    app = provider(
        registry_address, RegistryMode.INSTANCE, config_center=config_center(registry_address), metadata_type="local"
    )
    app.export(greeter_impl_type())

    async with app, zk(registry_address) as registry:
        [instance_id] = await registry.children(f"{root}/greeter-app")
        path = f"{root}/greeter-app/{instance_id}"
        # The MetadataService follows the services it describes.
        greeter_url, _, url = app.exported_urls
        assert (greeter_url.path, url.path) == ("test.registry.Greeter", "org.apache.dubbo.metadata.MetadataServiceV2")
        client = Dubbo(env_prefix=None)
        service = client.refer(MetadataServiceV2, url=str(url))

        async with client, registry.watch(path) as snapshots:
            with anyio.fail_after(5):
                first = json.loads(await anext(snapshots))["payload"]["metadata"]["dubbo.metadata.revision"]
                assert (await service.get_metadata_info(MetadataRequest(revision=first))).version == first

                await registry.set(
                    f"{root}/config/dubbo/greeter-app.configurators",
                    b"scope: application\nkey: greeter-app\nconfigs: [{side: provider, parameters: {weight: 50}}]\n",
                )
                data = await _until(
                    snapshots,
                    lambda data: (
                        bool(data) and json.loads(data)["payload"]["metadata"]["dubbo.metadata.revision"] != first
                    ),
                )
                current = json.loads(data)["payload"]["metadata"]["dubbo.metadata.revision"]
                await anyio.wait_all_tasks_blocked()

                assert (await service.get_metadata_info(MetadataRequest(revision=current))).version == current

                async def read_first_until_dropped() -> None:
                    while True:
                        await service.get_metadata_info(MetadataRequest(revision=first))
                        await anyio.sleep(0.01)

                # The provider drops the old revision once the registration that replaced it returns.
                with pytest.raises(RpcError, match="NOT_FOUND"):
                    await read_first_until_dropped()


async def test_local_metadata_over_tri_also_serves_the_version_older_consumers_know(
    registry_address, greeter_impl_type, provider, zk
):
    from dubbo.metadata.service.v1 import MetadataServiceV1

    root = "/" + URL.parse(registry_address).parameters["group"]
    app = provider(registry_address, RegistryMode.INSTANCE, metadata_type="local")
    app.export(greeter_impl_type())

    async with app, zk(registry_address) as registry:
        [instance_id] = await registry.children(f"{root}/greeter-app")
        async with registry.watch(f"{root}/greeter-app/{instance_id}") as snapshots:
            node = json.loads(await anext(snapshots))["payload"]["metadata"]
        published = json.loads(node["dubbo.metadata-service.url-params"])

        # A consumer that knows MetadataServiceV2 learns it from meta-v; one that does not calls what is published.
        assert node["meta-v"] == "2.0.0"
        paths = [url.path for url in app.exported_urls[1:]]
        assert paths == ["org.apache.dubbo.metadata.MetadataService", "org.apache.dubbo.metadata.MetadataServiceV2"]
        assert (published["protocol"], published["version"]) == ("tri", "1.0.0")
        client = Dubbo(env_prefix=None)
        service = client.refer(MetadataServiceV1, url=str(app.exported_urls[1]))
        async with client:
            info = await service.get_metadata_info(node["dubbo.metadata.revision"])

        assert info is not None
        assert [each.name for each in (info.services or {}).values()] == ["test.registry.Greeter"]


async def test_a_failure_to_register_what_the_rules_change_is_tried_again(
    registry_address, monkeypatch, caplog, greeter_impl_type, config_center, provider, zk
):
    root = "/" + URL.parse(registry_address).parameters["group"]
    register = ZookeeperInterfaceRegistry.register
    calls = 0

    @asynccontextmanager
    async def failing_once(registry, url):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("registry unreachable")
        async with register(registry, url):
            yield

    monkeypatch.setattr(ZookeeperInterfaceRegistry, "register", failing_once)
    monkeypatch.setattr(dubbo.registry.provider, "backoff", lambda: itertools.repeat(0))
    app = provider(registry_address, RegistryMode.INTERFACE, config_center=config_center(registry_address))
    app.export(greeter_impl_type())

    async with (
        app,
        zk(registry_address) as client,
        _registered_weights(client, root, RegistryMode.INTERFACE) as weights,
    ):
        assert await anext(weights) is None
        await client.set(
            f"{root}/config/dubbo/greeter-app.configurators",
            b"scope: application\nkey: greeter-app\nconfigs: [{side: provider, parameters: {weight: 50}}]\n",
        )
        assert await _until(weights, lambda value: value == "50") == "50"

    assert calls == 3
    assert "Cannot register the services as their override rules changed" in caplog.text


@pytest.mark.parametrize(
    ("metadata_type", "metadata_service"),
    [(MetadataType.LOCAL, ("2.0.0", "tri")), (MetadataType.REMOTE, (None, None))],
    ids=["local", "remote"],
)
async def test_a_consumer_calls_a_provider_found_by_application(
    registry_address, metadata_type, metadata_service, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    app = provider(registry_address, RegistryMode.INSTANCE, metadata_type=metadata_type)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INSTANCE)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            [instance_id] = await client.children(f"{root}/greeter-app")
            node = json.loads(await client.get(f"{root}/greeter-app/{instance_id}") or b"")
            mapping = await client.get(f"{root}/mapping/test.registry.Greeter")
            assert await client.children(f"{root}/test.registry.Greeter") == []

    metadata = node["payload"]["metadata"]
    assert instance_id == f"127.0.0.1:{node['port']}"
    assert mapping == b"greeter-app"
    assert metadata["dubbo.metadata.storage-type"] == str(metadata_type)
    assert json.loads(metadata["dubbo.endpoints"]) == [{"port": node["port"], "protocol": "tri"}]
    service_params = json.loads(metadata.get("dubbo.metadata-service.url-params", "{}"))
    assert (metadata.get("meta-v"), service_params.get("protocol")) == metadata_service


@dubbo.service("test.registry.Hello")
class _Hello(typing.Protocol):
    async def hello(self, name: str) -> str: ...


class _HelloImpl(_Hello):
    async def hello(self, name: str) -> str:
        return f"hello {name}"


@pytest.fixture
def instance_app(registry_config):
    def create(address: str, name: str, *, protocols=None, tls: TLSConfig | None = None) -> Dubbo:
        return Dubbo(
            application=ApplicationConfig(name=name, metadata_type=MetadataType.LOCAL),
            registries={"zk": registry_config(address, mode=RegistryMode.INSTANCE)},
            protocols=protocols,
            tls=tls,
            shutdown=ShutdownConfig(unregister_wait=0),
            env_prefix=None,
        )

    return create


@pytest.fixture
def instance_metadata(zk):
    async def read(address: str, app: str) -> dict[str, str]:
        root = "/" + URL.parse(address).parameters["group"]
        async with zk(address) as client:
            [instance_id] = await client.children(f"{root}/{app}")
            return json.loads(await client.get(f"{root}/{app}/{instance_id}") or b"")["payload"]["metadata"]

    return read


async def test_a_provider_served_only_over_dubbo_serves_its_metadata_through_the_metadata_service_1_0_0(
    registry_address,
    instance_app,
    instance_metadata,
):
    app = instance_app(
        registry_address, "hello-app", protocols={"dubbo": ProtocolConfig(name="dubbo", host="127.0.0.1", port=0)}
    )
    app.export(_HelloImpl())
    caller = instance_app(registry_address, "caller-app")
    hello = caller.refer(_Hello)

    async with app, caller:
        assert await hello.hello("b") == "hello b"
        metadata = await instance_metadata(registry_address, "hello-app")

    assert metadata["meta-v"] == "1.0.0"
    assert json.loads(metadata["dubbo.metadata-service.url-params"])["protocol"] == "dubbo"


async def test_local_metadata_shares_a_triple_server_tuned_by_its_protocol(
    registry_address, greeter_contract, greeter_impl_type, instance_app, consumer
):
    tuned = TripleConfig(max_receive_message_size=8 << 20, max_concurrent_streams=50)
    app = instance_app(
        registry_address,
        "greeter-app",
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0, triple=tuned)},
    )
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INSTANCE)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")


async def test_a_consumer_reads_local_metadata_over_tls_as_it_calls(
    registry_address, greeter_contract, greeter_impl_type, instance_app
):
    certificates = Path(__file__).resolve().parents[2] / "certificates"
    server = TLSConfig(certfile=certificates / "localhost-cert.pem", keyfile=certificates / "localhost-key.pem")
    client = TLSConfig(cafile=certificates / "localhost-cert.pem", server_hostname="localhost")
    app = instance_app(
        registry_address,
        "greeter-app",
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0)},
        tls=server,
    )
    app.export(greeter_impl_type())
    caller = instance_app(registry_address, "caller-app", tls=client)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")


async def test_all_registers_both_ways_and_consumers_discover_instances(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    app = provider(registry_address, RegistryMode.ALL)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.ALL)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            assert len(await client.children(f"{root}/test.registry.Greeter/providers")) == 1
            assert len(await client.children(f"{root}/greeter-app")) == 1


async def test_an_all_consumer_also_calls_providers_registered_by_interface_only(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider
):
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.ALL)
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")


async def test_references_share_the_watch_and_the_metadata_of_an_application(
    registry_address,
    monkeypatch,
    echo_contract,
    echo_impl_type,
    greeter_contract,
    greeter_impl_type,
    consumer,
    provider,
):
    subscribed: list[str] = []
    read: list[str] = []
    subscribe, get = ZookeeperInstanceRegistry.subscribe, MetadataStore.get

    def recording_subscribe(self: ZookeeperInstanceRegistry, app: str) -> typing.Any:
        subscribed.append(app)
        return subscribe(self, app)

    def recording_get(self: MetadataStore, revision: str) -> typing.Any:
        read.append(revision)
        return get(self, revision)

    monkeypatch.setattr(ZookeeperInstanceRegistry, "subscribe", recording_subscribe)
    monkeypatch.setattr(MetadataStore, "get", recording_get)
    app = provider(registry_address, RegistryMode.INSTANCE)
    app.export(greeter_impl_type())
    app.export(echo_impl_type())
    caller = consumer(registry_address, RegistryMode.INSTANCE)
    greeter, echo = caller.refer(greeter_contract), caller.refer(echo_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")
        assert await echo.echo(StringValue(value="b")) == StringValue(value="b")

    assert subscribed == ["greeter-app"]
    assert len(read) == 1


async def test_an_instance_whose_metadata_cannot_be_read_leaves_the_others_callable(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    good = provider(registry_address, RegistryMode.INSTANCE, name="good-app")
    good.export(greeter_impl_type("good"))
    bad = provider(registry_address, RegistryMode.INSTANCE, name="bad-app")
    bad.export(greeter_impl_type("bad"))
    caller = consumer(registry_address, RegistryMode.INSTANCE)
    greeter = caller.refer(greeter_contract)

    async with good, bad:
        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            [instance_id] = await client.children(f"{root}/bad-app")
            path = f"{root}/bad-app/{instance_id}"
            node = json.loads(await client.get(path) or b"")
            node["payload"]["metadata"]["dubbo.metadata-service.url-params"] = "[]"
            await client.set(path, json.dumps(node).encode())

        async with caller:
            answers = {(await greeter.greet(StringValue(value="b"))).value for _ in range(20)}

    assert answers == {"good: hello b"}


async def test_a_metadata_report_apart_from_the_registry_holds_the_metadata_and_the_mapping(
    registry_address, greeter_contract, greeter_impl_type, provider, registry_config, zk
):
    base, _, query = registry_address.partition("?")
    parameters = dict(parse_qsl(query))
    root = "/" + parameters.pop("group")
    report = MetadataReportConfig(
        address=base + (f"?{urlencode(parameters)}" if parameters else ""), group=f"{root}/report"
    )
    app = provider(registry_address, RegistryMode.INSTANCE, metadata_report=report, metadata_type=MetadataType.REMOTE)
    app.export(greeter_impl_type())
    caller = Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries={"zk": registry_config(registry_address, mode=RegistryMode.INSTANCE)},
        metadata_report=report,
        env_prefix=None,
    )
    greeter = caller.refer(greeter_contract)

    async with app, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")

        async with zk(registry_address) as client:
            assert len(await client.children(f"{root}/report/metadata/greeter-app")) == 1
            assert await client.get(f"{root}/report/mapping/test.registry.Greeter") is not None
            assert not {"metadata", "mapping"} & set(await client.children(root))


async def test_consumers_follow_the_applications_mapped_to_an_interface(
    registry_address, consumer_updates, greeter_contract, greeter_impl_type, consumer, provider
):
    first = provider(registry_address, RegistryMode.INSTANCE, name="first-app")
    first.export(greeter_impl_type("first"))
    second = provider(registry_address, RegistryMode.INSTANCE, name="second-app")
    second.export(greeter_impl_type("second"))
    caller = consumer(registry_address, RegistryMode.INSTANCE, routers=_UPDATES, loadbalance="roundrobin")
    greeter = caller.refer(greeter_contract)

    async with first, caller:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="first: hello b")
        since = len(consumer_updates.snapshots)
        async with second:
            await consumer_updates.wait_for(lambda urls: len(urls) == 2, since=since)
            answers = [(await greeter.greet(StringValue(value="b"))).value for _ in range(2)]
            assert set(answers) == {"first: hello b", "second: hello b"}


async def test_provided_by_skips_the_mapping(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider, zk
):
    app = provider(registry_address, RegistryMode.INSTANCE)
    app.export(greeter_impl_type())
    caller = consumer(registry_address, RegistryMode.INSTANCE, provided_by=("greeter-app",))
    greeter = caller.refer(greeter_contract)

    async with app:
        root = "/" + URL.parse(registry_address).parameters["group"]
        async with zk(registry_address) as client:
            await client.delete(f"{root}/mapping/test.registry.Greeter")

        async with caller:
            assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")


async def test_a_reference_without_providers_fails_its_calls_as_unavailable(
    registry_address, greeter_contract, consumer
):
    caller = consumer(registry_address, RegistryMode.ALL, check=False)
    greeter = caller.refer(greeter_contract)

    async with caller:
        with pytest.raises(RpcError, match="UNAVAILABLE") as raised:
            await greeter.greet(StringValue(value="b"))

    assert raised.value.status is Status.UNAVAILABLE


async def test_startup_fails_when_a_reference_that_checks_has_no_provider(
    registry_address, monkeypatch, greeter_contract, consumer
):
    monkeypatch.setattr("dubbo.application._CHECK_GRACE", 0.1)
    caller = consumer(registry_address, RegistryMode.INTERFACE)
    caller.refer(greeter_contract)

    with pytest.raises(RpcError, match="UNAVAILABLE") as raised:
        async with caller:
            pass

    assert raised.value.status is Status.UNAVAILABLE
    assert "test.registry.Greeter" in str(raised.value)


@pytest.mark.parametrize("mode", list(RegistryMode))
async def test_startup_fails_on_a_registry_scheme_without_an_implementation(
    mode, greeter_contract, greeter_impl_type, consumer, provider
):
    caller = consumer("etcd://127.0.0.1:2379", mode)
    caller.refer(greeter_contract)
    app = provider("etcd://127.0.0.1:2379", mode)
    app.export(greeter_impl_type())

    for application in (caller, app):
        with pytest.raises(ExtensionError, match="unknown extension 'etcd'"):
            async with application:
                pass


async def test_a_reference_finds_the_provider_its_own_application_registers(
    registry_address, greeter_contract, greeter_impl_type, provider
):
    app = provider(registry_address, RegistryMode.INTERFACE)
    app.export(greeter_impl_type())
    greeter = app.refer(greeter_contract)

    async with app:
        assert await greeter.greet(StringValue(value="b")) == StringValue(value="a: hello b")


async def test_an_all_consumer_calls_the_providers_found_by_instance_while_there_are_any(
    registry_address, greeter_contract, greeter_impl_type, consumer, provider
):
    by_instance = provider(registry_address, RegistryMode.INSTANCE, name="instance-app")
    by_instance.export(greeter_impl_type("instance"))
    by_interface = provider(registry_address, RegistryMode.INTERFACE, name="interface-app")
    by_interface.export(greeter_impl_type("interface"))
    caller = consumer(registry_address, RegistryMode.ALL)
    greeter = caller.refer(greeter_contract)

    async with by_instance, by_interface, caller:
        answers = {(await greeter.greet(StringValue(value="b"))).value for _ in range(20)}

    assert answers == {"instance: hello b"}


async def test_a_reference_of_several_registries_calls_the_preferred_one(
    registry_address, greeter_contract, greeter_impl_type, provider, registry_config
):
    root = URL.parse(registry_address).parameters["group"]
    other_address = registry_address.replace(f"group={root}", f"group={root}/other")

    def serving(address: str, name: str) -> Dubbo:
        app = provider(address, RegistryMode.INTERFACE, name=name)
        app.export(greeter_impl_type(name))
        return app

    caller = Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries={
            "one": registry_config(registry_address, mode=RegistryMode.INTERFACE),
            "two": registry_config(other_address, mode=RegistryMode.INTERFACE, preferred=True),
        },
        env_prefix=None,
    )
    greeter = caller.refer(greeter_contract)

    async with serving(registry_address, "one"), serving(other_address, "two"), caller:
        # The providers of the preferred registry take the calls once they are connected.
        with anyio.fail_after(5):
            while (await greeter.greet(StringValue(value="b"))).value != "two: hello b":
                await anyio.sleep(0.01)
        answers = {(await greeter.greet(StringValue(value="b"))).value for _ in range(20)}

    assert answers == {"two: hello b"}


async def _until(values, predicate):
    with anyio.fail_after(5):
        async for value in values:
            if predicate(value):
                return value
    pytest.fail("the watch ended before the expected change")


@asynccontextmanager
async def _registered_weights(client, root, mode):
    if mode is RegistryMode.INTERFACE:
        async with client.watch_children(f"{root}/test.registry.Greeter/providers") as snapshots:

            async def weights():
                async for nodes in snapshots:
                    if len(nodes) == 1:
                        yield _parse_full_string(unquote_plus(nodes[0])).parameters.get("weight")

            yield weights()
    else:
        [instance] = await client.children(f"{root}/greeter-app")
        async with client.watch(f"{root}/greeter-app/{instance}") as snapshots:

            async def weights():
                async for data in snapshots:
                    if data:
                        revision = json.loads(data)["payload"]["metadata"]["dubbo.metadata.revision"]
                        metadata = json.loads(await client.get(f"{root}/metadata/greeter-app/{revision}"))
                        [service] = metadata["services"].values()
                        yield service["params"].get("weight")

            yield weights()


async def test_an_instance_publishes_the_advertised_port_of_its_protocol_over_that_of_the_application(
    registry_address, registry_config, greeter_impl_type, instance_metadata
):
    app = Dubbo(
        application=ApplicationConfig(name="greeter-app", metadata_type=MetadataType.LOCAL, advertised_port=40000),
        registries={"zk": registry_config(registry_address, mode=RegistryMode.INSTANCE)},
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0, advertised_port=30051)},
        shutdown=ShutdownConfig(unregister_wait=0),
        env_prefix=None,
    )
    app.export(greeter_impl_type())

    async with app:
        metadata = await instance_metadata(registry_address, "greeter-app")

    assert json.loads(metadata["dubbo.endpoints"]) == [{"port": 30051, "protocol": "tri"}]
    assert json.loads(metadata["dubbo.metadata-service.url-params"])["port"] == "30051"
