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
import typing
from contextlib import AsyncExitStack

import anyio
import pytest

from dubbo.extension import ApplicationScope, extensions
from dubbo.registry import ServiceInstance
from dubbo.registry.zookeeper import ZookeeperInstanceRegistry
from dubbo.transport.zookeeper import ZookeeperClient, ZookeeperError
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_an_instance_watch_that_fails_after_the_first_instances_is_watched_again(memory_zookeeper, monkeypatch):
    client = extensions.get(ZookeeperClient, "memory")
    failures = 1

    class Flaky(client):
        def watch(self, path: str) -> typing.Any:
            nonlocal failures
            if path.endswith("10.0.0.6:50051") and failures:
                failures -= 1
                raise ZookeeperError("unreachable")
            return super().watch(path)

    monkeypatch.setattr("dubbo.utils.async_.backoff", lambda: itertools.repeat(0))
    extensions.register(ZookeeperClient, "flaky", Flaky)
    first = ServiceInstance(app="demo", host="10.0.0.5", port=50051)
    second = ServiceInstance(app="demo", host="10.0.0.6", port=50051)

    async with (
        ApplicationScope() as scope,
        AsyncExitStack() as stack,
        ZookeeperInstanceRegistry(
            URL.parse("zookeeper://127.0.0.1?client=flaky").replace(attributes={APPLICATION_SCOPE: scope})
        ) as discovery,
    ):
        await stack.enter_async_context(discovery.register(first))
        async with discovery.subscribe("demo") as updates:
            with anyio.fail_after(5):
                assert await anext(updates) == [first]

            await stack.enter_async_context(discovery.register(second))
            with anyio.fail_after(5):
                async for instances in updates:
                    if len(instances) == 2:
                        break

    assert sorted(instances, key=lambda instance: instance.id) == [first, second]

    assert failures == 0
