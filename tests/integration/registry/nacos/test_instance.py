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

import uuid

import anyio
import pytest

from dubbo.registry import ServiceInstance
from dubbo.registry.nacos import NacosInstanceRegistry
from dubbo.transport.nacos import DEFAULT_GROUP, NacosInstance, get_nacos_naming_client

pytestmark = [pytest.mark.anyio, pytest.mark.nacos]


@pytest.mark.parametrize(
    "query", ["", "group", "nacos-group"], ids=["default-group", "registry-group", "nacos-group-overrides"]
)
async def test_application_instances_use_the_application_service_and_selected_nacos_group(
    opened, register, group, query
):
    parameters, expected_group = {
        "": ("", DEFAULT_GROUP),
        "group": (f"group={group}", group),
        "nacos-group": (f"group=other&nacos.group={group}", group),
    }[query]
    registry = await opened(NacosInstanceRegistry, parameters)
    instance = ServiceInstance(
        app=f"orders-{uuid.uuid4().hex}", host="10.0.0.2", port=50051, metadata={"dubbo.metadata.revision": "a1"}
    )
    client = await get_nacos_naming_client(registry.url)
    raw = NacosInstance(host=instance.host, port=instance.port, metadata=instance.metadata)

    with anyio.fail_after(10):
        async with (
            registry.subscribe(instance.app) as snapshots,
            client.watch(instance.app, expected_group) as raw_snapshots,
        ):
            assert await anext(snapshots) == []
            release = await register(registry, instance)
            async for instances in snapshots:
                if instances:
                    break
            assert instances == [instance]
            async for instances in raw_snapshots:
                if instances:
                    break
            assert instances == [raw]

            await release()
            async for instances in snapshots:
                if not instances:
                    break
            assert instances == []
