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
from v2.nacos import ConfigParam

from dubbo.config_center.nacos import NacosConfigCenter
from dubbo.extension import ApplicationScope
from dubbo.transport.nacos import get_nacos_config_client
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.nacos]


@pytest.fixture
async def storage(nacos):
    group = f"dubbo-test-{uuid.uuid4().hex}"
    async with ApplicationScope() as scope:
        url = URL.parse(f"nacos://{nacos}").replace(attributes={APPLICATION_SCOPE: scope})
        client = await get_nacos_config_client(url)
        async with NacosConfigCenter(url) as center:
            yield center, client, group

        # The framework has no configuration deletion API.
        for key in ("dubbo.yaml", "rules"):
            await client._connected().remove_config(ConfigParam(data_id=key, group=group))


async def test_entries_are_read_and_watched_by_key_and_group(storage):
    center, client, group = storage
    with anyio.fail_after(10):
        async with client.watch("dubbo.yaml", group) as contents:
            assert await anext(contents) is None
            await client.update("dubbo.yaml", group, lambda _: "application: {name: orders}")
            async for content in contents:
                if content == "application: {name: orders}":
                    break

    assert await center.get("dubbo.yaml", group=group) == "application: {name: orders}"
    assert await center.get("missing.yaml", group=group) is None
    assert await center.get("dubbo.yaml", group=group + "-other") is None

    with anyio.fail_after(10):
        async with center.watch("rules", group=group) as contents:
            assert await anext(contents) is None
            await client.update("rules", group, lambda _: "force: true")
            async for content in contents:
                if content == "force: true":
                    break

    assert content == "force: true"
