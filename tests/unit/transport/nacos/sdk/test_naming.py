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

import asyncio
from types import SimpleNamespace

import anyio
import pytest
from v2.nacos import Instance

from dubbo.transport.nacos import NacosInstance
from dubbo.transport.nacos.sdk import naming
from dubbo.transport.nacos.sdk.naming import SdkNacosNamingClient
from dubbo.url import URL


@pytest.mark.anyio
async def test_sdk_watch_leaves_out_unhealthy_or_disabled_instances(monkeypatch):
    class Naming:
        grpc_client_proxy = None

        def __init__(self):
            self.grpc_client_proxy = self
            self.unsubscribed = []

        async def start(self):
            self.redo_service = SimpleNamespace(_listen_task=asyncio.create_task(anyio.sleep_forever()))

        async def shutdown(self):
            pass

        async def subscribe(self, param):
            pass

        async def unsubscribe(self, param):
            self.unsubscribed.append((param.service_name, param.group_name))

        async def list_instances(self, param):
            return [
                Instance(ip="h", port=1, metadata={"a": "b"}),
                Instance(ip="h", port=2, healthy=False),
                Instance(ip="h", port=3, enabled=False),
            ]

    service = Naming()
    monkeypatch.setattr(naming, "NacosNamingService", lambda settings: service)

    async with SdkNacosNamingClient(URL.parse("nacos://n")) as client, client.watch("service", "group") as snapshots:
        with anyio.fail_after(5):
            assert await anext(snapshots) == [NacosInstance(host="h", port=1, metadata={"a": "b"})]

    assert service.unsubscribed == [("service", "group")]


class _Registering:
    """A naming service that records what it holds of each service, by host and port, and fails when told."""

    def __init__(self):
        self.grpc_client_proxy = self
        self.held = {}
        self.failures = []
        # Whether a registration the server has taken waits, as the SDK does for its redo state.
        self.hanging = False

    async def start(self):
        self.redo_service = SimpleNamespace(_listen_task=asyncio.create_task(anyio.sleep_forever()))

    async def shutdown(self):
        pass

    async def register_instance(self, param):
        return await self.batch_register_instances(SimpleNamespace(instances=[param]))

    async def batch_register_instances(self, param):
        if self.failures:
            raise self.failures.pop()
        self.held = {(instance.ip, instance.port): dict(instance.metadata) for instance in param.instances}
        if self.hanging:
            await anyio.sleep_forever()
        return True

    async def deregister_instance(self, param):
        self.held.pop((param.ip, param.port), None)
        return True


@pytest.fixture
def registering(monkeypatch):
    service = _Registering()
    monkeypatch.setattr(naming, "NacosNamingService", lambda settings: service)
    return service


@pytest.mark.anyio
async def test_sdk_leaves_an_instance_kept_again_at_its_address_as_the_earlier_keeper_exits(registering):
    old = NacosInstance(host="h", port=1, metadata={"weight": "100"})
    new = NacosInstance(host="h", port=1, metadata={"weight": "50"})

    async with SdkNacosNamingClient(URL.parse("nacos://n")) as client:
        earlier = client.keep_registered("service", "group", old)
        await earlier.__aenter__()
        async with client.keep_registered("service", "group", new):
            await earlier.__aexit__(None, None, None)
            held = dict(registering.held)

    assert (held, registering.held) == ({("h", 1): {"weight": "50"}}, {})


@pytest.mark.anyio
async def test_sdk_that_fails_to_keep_an_instance_holds_again_what_it_held_before(registering):
    kept = NacosInstance(host="h", port=1, metadata={"weight": "100"})
    other = NacosInstance(host="h", port=2)

    async with SdkNacosNamingClient(URL.parse("nacos://n")) as client, client.keep_registered("s", "g", kept):
        registering.failures.append(ConnectionError("the connection was lost after the request went out"))
        registering.held[("h", 2)] = {}
        with pytest.raises(ConnectionError):
            async with client.keep_registered("s", "g", other):
                pytest.fail("the instance was not registered")

        assert registering.held == {("h", 1): {"weight": "100"}}


@pytest.mark.anyio
async def test_sdk_cancelled_while_keeping_an_instance_holds_again_what_it_held_before(registering):
    async with SdkNacosNamingClient(URL.parse("nacos://n")) as client:
        registering.hanging = True
        with anyio.move_on_after(0.1):
            async with client.keep_registered("s", "g", NacosInstance(host="h", port=1)):
                pytest.fail("the instance was not registered")

        assert registering.held == {}


@pytest.mark.anyio
async def test_sdk_watch_cancelled_while_subscribing_leaves_no_callback(monkeypatch):
    class Naming:
        def __init__(self):
            self.grpc_client_proxy = self
            self.callbacks = []

        async def start(self):
            self.redo_service = SimpleNamespace(_listen_task=asyncio.create_task(anyio.sleep_forever()))

        async def shutdown(self):
            pass

        async def subscribe(self, param):
            # The SDK holds the callback before the server answers.
            self.callbacks.append(param.subscribe_callback)
            await anyio.sleep_forever()

        async def unsubscribe(self, param):
            self.callbacks.remove(param.subscribe_callback)

    service = Naming()
    monkeypatch.setattr(naming, "NacosNamingService", lambda settings: service)

    async with SdkNacosNamingClient(URL.parse("nacos://n")) as client:
        with anyio.move_on_after(0.1):
            async with client.watch("service", "group"):
                pytest.fail("the watch was not cancelled")

        assert service.callbacks == []
