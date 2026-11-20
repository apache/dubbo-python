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

import anyio
import pytest

from dubbo import Dubbo
from dubbo.config_center.zookeeper import ZookeeperConfigCenter
from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_entry_is_the_node_under_namespace_config_group_key(memory_zookeeper):
    memory_zookeeper.put("/dubbo/config/dubbo/dubbo.yaml", b"application: {name: default}")
    memory_zookeeper.put("/prod/config/orders/app.yaml", "application: {name: 订单}".encode())
    center = {"address": "zookeeper://zk:2181?client=memory"}

    async with Dubbo({"config_center": center}, env_prefix=None) as default:
        assert default.config.application.name == "default"
    custom = {**center, "group": "orders", "config_file": "app.yaml", "namespace": "prod"}
    async with Dubbo({"config_center": custom}, env_prefix=None) as prod:
        assert prod.config.application.name == "订单"


async def test_centers_of_one_ensemble_share_a_connection_within_an_application(memory_zookeeper):
    first = URL.parse("zookeeper://zk:2181?client=memory&namespace=a&timeout=5000")
    second = URL.parse("zookeeper://zk:2181?client=memory&namespace=b&timeout=5000")

    async with (
        ApplicationScope() as scope,
        ZookeeperConfigCenter(first.replace(attributes={APPLICATION_SCOPE: scope})) as a,
        ZookeeperConfigCenter(second.replace(attributes={APPLICATION_SCOPE: scope})) as b,
    ):
        assert await a.get("a", group="orders") is None
        assert await b.get("b", group="billing") is None

    assert len(memory_zookeeper.urls) == 1


async def test_watch_decodes_the_text(memory_zookeeper):
    memory_zookeeper.put("/dubbo/config/dubbo/rules", b"rule")
    url = URL.parse("zookeeper://zk?client=memory")

    async with (
        ApplicationScope() as scope,
        ZookeeperConfigCenter(url.replace(attributes={APPLICATION_SCOPE: scope})) as center,
        center.watch("rules", group="dubbo") as values,
    ):
        with anyio.fail_after(5):
            assert await anext(values) == "rule"
