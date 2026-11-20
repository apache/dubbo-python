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
from contextlib import asynccontextmanager

import anyio
import pytest

from dubbo.extension import ApplicationScope, Resource, extensions
from dubbo.registry.nacos import NacosInterfaceRegistry
from dubbo.transport.nacos import NacosInstance, NacosNamingClient
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_an_instance_that_holds_no_valid_url_is_left_out_of_the_others(isolated_extensions, caplog):
    caplog.set_level(logging.WARNING)
    bad = NacosInstance(host="10.0.0.1", port=1, metadata={"protocol": "bad protocol", "path": "test.Greeter"})
    good = NacosInstance(host="10.0.0.2", port=2, metadata={"protocol": "tri", "path": "test.Greeter"})

    class Snapshot(Resource):
        def __init__(self, url: URL) -> None:
            pass

        async def aclose(self) -> None:
            pass

        @asynccontextmanager
        async def watch(self, service: str, group: str):
            async def snapshots():
                yield [bad, good]
                await anyio.sleep_forever()

            yield snapshots()

    extensions.register(NacosNamingClient, "snapshot", Snapshot)

    async with (
        ApplicationScope() as scope,
        NacosInterfaceRegistry(
            URL.parse("nacos://127.0.0.1:8848?client=snapshot").replace(attributes={APPLICATION_SCOPE: scope})
        ) as registry,
        registry.subscribe("test.Greeter", group=None, version=None) as updates,
    ):
        with anyio.fail_after(5):
            urls = await anext(updates)

    assert [url.host for url in urls] == ["10.0.0.2"]
    assert "Ignoring the instance 10.0.0.1:1" in caplog.text
