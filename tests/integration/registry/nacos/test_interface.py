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

from contextlib import AsyncExitStack

import anyio
import pytest

from dubbo.registry.nacos import NacosInterfaceRegistry
from dubbo.transport.nacos import DEFAULT_GROUP, NacosInstance, get_nacos_naming_client
from dubbo.url import URL

pytestmark = [pytest.mark.anyio, pytest.mark.nacos]


async def _snapshot(registry, service, group, expected):
    client = await get_nacos_naming_client(registry.url)
    async with client.watch(service, group) as snapshots:
        with anyio.fail_after(10):
            async for instances in snapshots:
                if set(instances) == set(expected):
                    return sorted(instances, key=lambda instance: (instance.host, instance.port))
    pytest.fail("the naming watch ended before the expected instances")


async def test_provider_registration_uses_category_interface_version_and_group(opened, register, provider_url, group):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")
    expected = NacosInstance(
        host="10.0.0.1",
        port=50051,
        metadata={**provider_url.parameters, "category": "providers", "protocol": "tri", "path": provider_url.path},
    )
    service = f"providers:{provider_url.path}:1.0.0:blue"

    release = await register(registry, provider_url)

    assert await _snapshot(registry, service, group, [expected]) == [expected]
    await release()
    assert await _snapshot(registry, service, group, []) == []


async def test_missing_version_and_group_use_empty_service_segments_and_the_default_nacos_group(
    opened, register, provider_url
):
    registry = await opened(NacosInterfaceRegistry)
    url = provider_url.replace(parameters={"interface": provider_url.path})
    expected = NacosInstance(
        host=url.host,
        port=url.port,
        metadata={**url.parameters, "category": "providers", "protocol": "tri", "path": url.path},
    )

    await register(registry, url)

    assert await _snapshot(registry, f"providers:{url.path}::", DEFAULT_GROUP, [expected]) == [expected]


async def _register_a_consumer(opened, register, provider_url, group, query):
    """Register a consumer URL, as a reference has it with no port, then a provider; return the registry and the consumer URL.

    The provider registers after the consumer on the same connection, so once it shows, so has the consumer.
    """
    registry = await opened(NacosInterfaceRegistry, f"group={group}{query}")
    url = provider_url.replace(protocol="consumer", port=None).update_parameters(
        {"category": "consumers", "side": "consumer"}
    )
    sentinel = NacosInstance(
        host=provider_url.host,
        port=provider_url.port,
        metadata={**provider_url.parameters, "category": "providers", "protocol": "tri", "path": provider_url.path},
    )

    await register(registry, url)
    await register(registry, provider_url)
    await _snapshot(registry, f"providers:{url.path}:1.0.0:blue", group, [sentinel])
    return registry, url


async def test_consumers_are_not_registered_by_default(opened, register, provider_url, group):
    registry, url = await _register_a_consumer(opened, register, provider_url, group, "")

    assert await _snapshot(registry, f"consumers:{url.path}:1.0.0:blue", group, []) == []


async def test_a_consumer_registers_with_port_0_when_requested(opened, register, provider_url, group):
    registry, url = await _register_a_consumer(opened, register, provider_url, group, "&register-consumer-url=true")
    expected = [
        NacosInstance(host=url.host, port=0, metadata={**url.parameters, "protocol": "consumer", "path": url.path})
    ]

    assert await _snapshot(registry, f"consumers:{url.path}:1.0.0:blue", group, expected) == expected


async def test_subscribers_receive_provider_urls_after_registration_changes(opened, register, provider_url, group):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")
    other = provider_url.replace(host="10.0.0.2")
    first = provider_url.update_parameters({"category": "providers"})
    second = other.update_parameters({"category": "providers"})

    with anyio.fail_after(10):
        async with registry.subscribe(provider_url.path, group="blue", version="1.0.0") as snapshots:
            assert await anext(snapshots) == []
            await register(registry, provider_url)
            async for urls in snapshots:
                if urls:
                    break
            assert urls == [first]
            await register(registry, other)
            async for urls in snapshots:
                if any(url.host == other.host for url in urls):
                    break
            assert set(urls) == {first, second}


async def test_unregistering_one_address_of_a_service_keeps_the_others(opened, register, provider_url, group):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")
    other = provider_url.replace(host="10.0.0.2")
    release = await register(registry, provider_url)
    await register(registry, other)
    service = f"providers:{provider_url.path}:1.0.0:blue"
    expected = NacosInstance(
        host=other.host,
        port=other.port,
        metadata={**other.parameters, "category": "providers", "protocol": "tri", "path": other.path},
    )

    await release()

    assert await _snapshot(registry, service, group, [expected]) == [expected]


async def test_subscribers_combine_providers_from_each_requested_group(opened, register, provider_url, group):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")
    green = provider_url.replace(host="10.0.0.2").update_parameters({"group": "green"})
    await register(registry, provider_url)
    await register(registry, green)

    with anyio.fail_after(10):
        async with registry.subscribe(provider_url.path, group="blue,green", version="1.0.0") as snapshots:
            async for urls in snapshots:
                if len(urls) == 2:
                    break

    assert set(urls) == {
        provider_url.update_parameters({"category": "providers"}),
        green.update_parameters({"category": "providers"}),
    }


@pytest.mark.parametrize(("wanted_group", "version"), [("*", "1.0.0"), ("blue", "*")], ids=["any-group", "any-version"])
async def test_subscribers_must_name_their_groups_and_version(opened, provider_url, group, wanted_group, version):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")

    with pytest.raises(ValueError, match="cannot watch any group or version"):
        async with registry.subscribe(provider_url.path, group=wanted_group, version=version):
            pass


async def test_subscribers_skip_protocol_less_instances_and_accept_a_missing_path(opened, provider_url, group):
    registry = await opened(NacosInterfaceRegistry, f"group={group}")
    client = await get_nacos_naming_client(registry.url)
    other = await opened(NacosInterfaceRegistry, f"group={group}")
    other_client = await get_nacos_naming_client(other.url)
    service = f"providers:{provider_url.path}::"
    good = NacosInstance(host="10.0.0.1", port=50051, metadata={"protocol": "tri", "interface": provider_url.path})
    bad = NacosInstance(host="10.0.0.1", port=50052, metadata={"interface": provider_url.path})

    async with AsyncExitStack() as registered:
        await registered.enter_async_context(client.keep_registered(service, group, good))
        await registered.enter_async_context(other_client.keep_registered(service, group, bad))
        await _snapshot(registry, service, group, [good, bad])

        with anyio.fail_after(10):
            async with registry.subscribe(provider_url.path, group=None, version=None) as snapshots:
                urls = await anext(snapshots)

    assert urls == [URL(protocol="tri", host=good.host, port=good.port, parameters={"interface": provider_url.path})]
