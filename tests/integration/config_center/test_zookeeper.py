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

from dubbo import Dubbo
from dubbo.config import ConfigCenterConfig
from dubbo.config_center.zookeeper import ZookeeperConfigCenter
from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.zookeeper]


async def test_application_reads_its_configuration_from_zookeeper(namespace, zookeeper, zk):
    async with zk(f"zookeeper://{zookeeper}") as client:
        await client.set(f"/{namespace}/config/dubbo/dubbo.yaml", b"application: {name: from-zookeeper}")

    center = ConfigCenterConfig(address=f"zookeeper://{zookeeper}", namespace=namespace)
    async with Dubbo(env_prefix=None, config_center=center) as app:
        assert app.config.application.name == "from-zookeeper"


async def test_watch_follows_the_node(namespace, zookeeper, zk):
    url = URL.parse(f"zookeeper://{zookeeper}?namespace={namespace}")

    async with (
        ApplicationScope() as scope,
        ZookeeperConfigCenter(url.replace(attributes={APPLICATION_SCOPE: scope})) as center,
        center.watch("dubbo.yaml", group="dubbo") as values,
    ):
        with anyio.fail_after(5):
            assert await anext(values) is None
            async with zk(f"zookeeper://{zookeeper}") as writer:
                await writer.set(f"/{namespace}/config/dubbo/dubbo.yaml", b"retries: 1")
            assert await anext(values) == "retries: 1"


@pytest.fixture
async def namespace(zookeeper, delete_tree, zk):
    name = f"dubbo-python-test-{uuid.uuid4().hex}"
    yield name
    async with zk(f"zookeeper://{zookeeper}") as client:
        await delete_tree(client, f"/{name}")
