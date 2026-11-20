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
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from typing import Any

import anyio
import pytest
from v2.nacos import ConfigParam

from dubbo.extension import ApplicationScope
from dubbo.transport.nacos import (
    NacosInstance,
    get_nacos_config_client,
    get_nacos_naming_client,
)
from dubbo.transport.nacos.sdk.config import SdkNacosConfigClient
from dubbo.transport.nacos.sdk.naming import SdkNacosNamingClient
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


# The SDK connects through the threads of grpcio.
@pytest.mark.real_clock
@pytest.mark.parametrize("client_type", [SdkNacosConfigClient, SdkNacosNamingClient], ids=["config", "naming"])
async def test_a_cancelled_connection_leaves_no_task_of_the_sdk(client_type: type) -> None:
    before = asyncio.all_tasks()

    with anyio.move_on_after(0.2):
        await client_type(URL.parse("nacos://127.0.0.1:1")).__aenter__()
    started = asyncio.all_tasks() - before - {asyncio.current_task()}
    # The SDK starts some tasks without keeping them, such as reading its disk cache; they end by themselves.
    with anyio.move_on_after(1):
        for task in started:
            await asyncio.wait((task,))

    assert [task for task in started if not task.done()] == []


async def _until(values: AsyncIterator[Any], expected: Callable[[Any], bool]) -> Any:
    with anyio.fail_after(10):
        async for value in values:
            if expected(value):
                return value
    raise AssertionError("the values ended")


@pytest.mark.nacos
async def test_sdk_watches_instances_until_none_are_left(nacos):
    service, group = f"providers:test.Nacos$Inner{uuid.uuid4().hex}::", "dubbo-test"
    instance = NacosInstance(host="10.9.9.9", port=1234, metadata={"side": "provider"})

    async with ApplicationScope() as scope:
        client = await get_nacos_naming_client(
            URL.parse(f"nacos://{nacos}").replace(attributes={APPLICATION_SCOPE: scope})
        )
        async with client.watch(service, group) as snapshots:
            assert await _until(snapshots, lambda instances: instances == []) == []
            async with client.keep_registered(service, group, instance):
                await _until(snapshots, lambda instances: instances == [instance])
            await _until(snapshots, lambda instances: instances == [])


@pytest.mark.nacos
async def test_sdk_keeps_an_instance_kept_again_when_the_keeper_it_replaced_exits(nacos):
    service, group = f"providers:test.Nacos{uuid.uuid4().hex}::", "dubbo-test"
    old = NacosInstance(host="10.9.9.9", port=1234, metadata={"weight": "100"})
    new = NacosInstance(host="10.9.9.9", port=1234, metadata={"weight": "53"})

    async with ApplicationScope() as scope:
        client = await get_nacos_naming_client(
            URL.parse(f"nacos://{nacos}").replace(attributes={APPLICATION_SCOPE: scope})
        )
        async with client.watch(service, group) as snapshots:
            async with AsyncExitStack() as stack:
                earlier = AsyncExitStack()
                await earlier.enter_async_context(client.keep_registered(service, group, old))
                await _until(snapshots, lambda instances: instances == [old])
                await stack.enter_async_context(client.keep_registered(service, group, new))
                await earlier.aclose()
                await _until(snapshots, lambda instances: instances == [new])
            await _until(snapshots, lambda instances: instances == [])


@pytest.fixture
async def config(nacos):
    data_id, group = f"test/{uuid.uuid4().hex}$x", "dubbo-test"
    async with ApplicationScope() as scope:
        client = await get_nacos_config_client(
            URL.parse(f"nacos://{nacos}").replace(attributes={APPLICATION_SCOPE: scope})
        )
        yield client, data_id, group

        # The framework has no configuration deletion API.
        assert isinstance(client, SdkNacosConfigClient)
        await client._connected().remove_config(
            ConfigParam(data_id=data_id.replace("$", "___").replace("/", "-"), group=group)
        )


@pytest.mark.nacos
async def test_sdk_writes_configurations_by_compare_and_set_and_watches_them(config):
    client, data_id, group = config

    async with client.watch(data_id, group) as contents:
        assert await _until(contents, lambda content: content is None) is None
        await client.update(data_id, group, lambda content: (content or "") + "a")
        await _until(contents, lambda content: content == "a")
        await client.update(data_id, group, lambda content: f"{content}b")
        await _until(contents, lambda content: content == "ab")

    assert await client.get(data_id, group) == "ab"


@pytest.mark.nacos
async def test_a_config_client_disconnects_without_waiting_for_its_listen_task(nacos):
    client = SdkNacosConfigClient(URL.parse(f"nacos://{nacos}"))
    await client.__aenter__()
    # As in a client that has run a while: the listen task waits for work.
    await anyio.wait_all_tasks_blocked()

    # The listen task of the SDK sees that it stops only every five seconds, unless cancelled.
    with anyio.fail_after(2):
        await client.aclose()
