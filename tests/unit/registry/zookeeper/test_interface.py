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
import pytest

from dubbo.extension import ApplicationScope
from dubbo.registry.zookeeper import ZookeeperInterfaceRegistry
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_a_node_that_holds_no_url_is_ignored_without_logging_its_name(memory_zookeeper, caplog):
    caplog.set_level(logging.WARNING)
    parent = "/dubbo/test.Greeter/providers"
    memory_zookeeper.put(f"{parent}/no-scheme%3Ftoken%3Dsecret", b"")
    memory_zookeeper.put(f"{parent}/tri%3A%2F%2F10.0.0.1%3A50051%2Ftest.Greeter", b"")

    async with (
        ApplicationScope() as scope,
        ZookeeperInterfaceRegistry(
            URL.parse("zookeeper://127.0.0.1?client=memory").replace(attributes={APPLICATION_SCOPE: scope})
        ) as registry,
        registry.subscribe("test.Greeter", group=None, version=None) as updates,
    ):
        with anyio.fail_after(5):
            urls = await anext(updates)

    assert [url.host for url in urls] == ["10.0.0.1"]
    assert f"Ignoring a node in {parent}" in caplog.text
    assert "secret" not in caplog.text
