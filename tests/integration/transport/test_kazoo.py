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
from collections.abc import AsyncIterator
from typing import Any

import anyio
import pytest
from kazoo.client import KazooClient
from kazoo.exceptions import NoAuthError

from dubbo.transport.zookeeper import ZookeeperClient, ZookeeperError
from dubbo.transport.zookeeper.kazoo import KazooZookeeperClient
from dubbo.url import URL

pytestmark = [pytest.mark.anyio, pytest.mark.zookeeper]


@pytest.fixture
async def client(zookeeper: str, zk) -> AsyncIterator[Any]:
    async with zk(f"zookeeper://{zookeeper}?timeout=5000") as client:
        yield client


async def test_leaving_watches_of_an_idle_node_keeps_none_of_their_callbacks(connected) -> None:
    client, root = connected
    path = f"{root}/rules"
    kazoo = client._kazoo
    listeners = len(kazoo.state_listeners)
    await client.set(path, b"rules")

    for _ in range(3):
        async with client.watch(path) as values, client.watch_children(path) as children:
            with anyio.fail_after(5):
                assert await anext(values) == b"rules"
                assert await anext(children) == []

    # Kazoo shows its registered watchers only through these attributes.
    assert len(kazoo.state_listeners) == listeners
    assert not kazoo._data_watchers.get(path)
    assert not kazoo._child_watchers.get(path)


@pytest.fixture
async def connected(client, delete_tree):
    root = f"/dubbo-python-test/{uuid.uuid4().hex}"
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


async def test_watches_resume_after_the_session_expires(connected, zookeeper):
    client, root = connected
    data, providers = f"{root}/config", f"{root}/providers"
    await client.set(data, b"v1")
    await client.create(f"{providers}/a")

    async with client.watch(data) as values, client.watch_children(providers) as names:
        assert await _next(values) == b"v1"
        assert await _next(names) == ["a"]

        await _expire_session(client, zookeeper)

        await client.set(data, b"v2")
        await _until(values, b"v2")
        await client.delete(f"{providers}/a")
        await _until(names, [])


async def test_kept_ephemeral_nodes_return_after_the_session_expires_until_their_keepers_exit(connected, zookeeper):
    client, root = connected
    kept, left = f"{root}/providers/a", f"{root}/providers/b"
    async with client.keep_ephemeral(kept, b"a"):
        async with client.keep_ephemeral(left, b"b"):
            pass

        await _expire_session(client, zookeeper)

        async with client.watch(kept) as values:
            await _until(values, b"a")
        assert await client.get(left) is None


async def test_a_later_keeper_changes_the_data_of_the_node_in_place(connected):
    client, root = connected
    path = f"{root}/instances/a"

    def created() -> int:
        return client._kazoo.exists(path).czxid

    async with client.keep_ephemeral(path, b"old"):
        first = await anyio.to_thread.run_sync(created)
        async with client.keep_ephemeral(path, b"new"):
            # Watchers would see the node missing if it were deleted and created again.
            assert await anyio.to_thread.run_sync(created) == first
            assert await client.get(path) == b"new"


async def _expire_session(client: ZookeeperClient, zookeeper: str) -> None:
    """Expire the session of ``client`` and wait until it has a new one."""
    # ZooKeeper expires a session that another client opens and closes.
    assert isinstance(client, KazooZookeeperClient)
    kazoo = client._kazoo
    expired = kazoo.client_id
    session = KazooClient(hosts=zookeeper, client_id=expired)

    def expire() -> None:
        session.start()
        session.stop()
        session.close()

    connected = anyio.Event()
    token = anyio.lowlevel.current_token()

    def changed(state):
        if state == "CONNECTED" and kazoo.client_id != expired:
            anyio.from_thread.run_sync(connected.set, token=token)

    kazoo.add_listener(changed)
    with anyio.fail_after(10):
        await anyio.to_thread.run_sync(expire)
        await connected.wait()
    kazoo.remove_listener(changed)


async def test_created_nodes_are_unreadable_to_other_users(client, zookeeper):
    path = f"/dubbo-python-test-acl-{uuid.uuid4().hex}"

    async with (
        KazooZookeeperClient(URL.parse(f"zookeeper://test-{uuid.uuid4().hex}:secret@{zookeeper}")) as owner,
        owner.keep_ephemeral(path, b"owned"),
    ):
        assert await owner.get(path) == b"owned"

        with pytest.raises(ZookeeperError, match="cannot get") as caught:
            await client.get(path)
        assert isinstance(caught.value.__cause__, NoAuthError)


async def test_created_nodes_without_a_user_are_readable_to_all(client, zookeeper):
    path = f"/dubbo-python-test-acl-{uuid.uuid4().hex}"

    async with (
        KazooZookeeperClient(URL.parse(f"zookeeper://{zookeeper}")) as owner,
        owner.keep_ephemeral(path, b"owned"),
    ):
        assert await owner.get(path) == b"owned"

        assert await client.get(path) == b"owned"
