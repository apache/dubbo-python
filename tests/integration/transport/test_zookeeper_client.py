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

"""The contract of ``ZookeeperClient``, held by the in-memory fake the unit tests use and by the kazoo client.

The tests arrange nodes with the operations that `zk` adds to the contract.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import anyio
import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture(params=["memory", pytest.param("kazoo", marks=pytest.mark.zookeeper)])
def address(request) -> str:
    if request.param == "memory":
        request.getfixturevalue("memory_zookeeper")
        return "zookeeper://127.0.0.1:2181?client=memory&timeout=5000"
    return f"zookeeper://{request.getfixturevalue('zookeeper')}?timeout=5000"


@pytest.fixture
async def connected(address, delete_tree, zk) -> AsyncIterator[tuple[Any, str]]:
    root = f"/dubbo-python-test/{uuid.uuid4().hex}"
    async with zk(address) as client:
        yield client, root
        await delete_tree(client, root)


async def _next(values: AsyncIterator[object]) -> object:
    with anyio.fail_after(5):
        return await anext(values)


async def _until(values: AsyncIterator[object], expected: object) -> None:
    with anyio.fail_after(5):
        async for value in values:
            if value == expected:
                return
    pytest.fail("the watch ended before the expected value")


async def test_a_missing_node_has_no_data(connected):
    client, root = connected

    assert await client.get(f"{root}/missing") is None


async def test_a_kept_ephemeral_node_replaces_one_that_exists_and_stays_as_its_earlier_keeper_exits(connected):
    client, root = connected
    await client.set(f"{root}/a/config", b"two")

    async with AsyncExitStack() as later:
        async with client.keep_ephemeral(f"{root}/a/provider"):
            await later.enter_async_context(client.keep_ephemeral(f"{root}/a/provider", b"replaced"))

        assert await client.get(f"{root}/a/provider") == b"replaced"
        assert sorted(await client.children(f"{root}/a")) == ["config", "provider"]
    assert await client.children(f"{root}/a") == ["config"]


async def test_data_watch_yields_the_current_data_then_changes(connected):
    client, root = connected
    path = f"{root}/rules"

    async with client.watch(path) as values:
        assert await _next(values) is None

        await client.set(path, b"one")
        assert await _next(values) == b"one"

        await client.delete(path)
        assert await _next(values) is None


async def test_children_watch_follows_the_node_as_it_is_deleted_and_created_again(connected):
    client, root = connected
    path = f"{root}/providers"

    async with client.watch_children(path) as values:
        assert await _next(values) == []
        assert await client.get(path) is None

        # Creating a child creates the node first, which may show no names.
        await client.create(f"{path}/a")
        await _until(values, ["a"])

        await client.delete(f"{path}/a")
        await client.delete(path)
        assert await _next(values) == []

        await client.create(f"{path}/b")
        await _until(values, ["b"])


async def test_update_changes_the_data_it_reads_and_creates_a_missing_node(connected):
    client, root = connected
    path = f"{root}/a/counter"
    seen = []

    def increment(data: bytes | None) -> bytes:
        seen.append(data)
        return b"1" if data is None else str(int(data) + 1).encode()

    await client.update(path, increment)
    await client.update(path, increment)

    assert seen == [None, b"1"]
    assert await client.get(path) == b"2"


async def test_closing_a_client_deletes_its_ephemeral_nodes(connected, address, zk):
    client, root = connected
    await client.set(f"{root}/kept", b"")

    # A keeper whose client closes before it exits.
    async with zk(address) as other:
        keeper = other.keep_ephemeral(f"{root}/provider")
        await keeper.__aenter__()
        assert sorted(await client.children(root)) == ["kept", "provider"]

    async with client.watch_children(root) as children:
        await _until(children, ["kept"])
    await keeper.__aexit__(None, None, None)
