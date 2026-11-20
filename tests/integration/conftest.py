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

"""Fixtures of the tests that run real ZooKeeper or Nacos servers, which their variables name."""

import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from anyio import to_thread
from kazoo.exceptions import NodeExistsError, NoNodeError

from dubbo.extension import ApplicationScope
from dubbo.protocol.triple import TripleProtocol
from dubbo.transport.zookeeper import get_zookeeper_client
from dubbo.transport.zookeeper.kazoo import KazooZookeeperClient
from dubbo.url import APPLICATION_SCOPE, URL

# The servers a marker needs, by the variable that holds their host:port.
_SERVERS = {"zookeeper": "DUBBO_TEST_ZOOKEEPER", "nacos": "DUBBO_TEST_NACOS"}


def pytest_runtest_setup(item: pytest.Item) -> None:
    for marker, variable in _SERVERS.items():
        if item.get_closest_marker(marker) and not os.environ.get(variable):
            pytest.skip(f"set {variable} to host:port")


@pytest.fixture
def zookeeper() -> str:
    """The host:port of the ZooKeeper that tests marked ``zookeeper`` use."""
    return os.environ[_SERVERS["zookeeper"]]


@pytest.fixture
def nacos() -> str:
    """The host:port of the Nacos that tests marked ``nacos`` use."""
    return os.environ[_SERVERS["nacos"]]


@pytest.fixture
def exported_urls(monkeypatch) -> list[URL]:
    """The URLs of the services exported over Triple, in export order."""
    urls = []
    export = TripleProtocol.export

    async def record(protocol, *args):
        exporter = await export(protocol, *args)
        urls.append(exporter.url)
        return exporter

    # Dubbo does not expose the port assigned to an exported service.
    monkeypatch.setattr(TripleProtocol, "export", record)
    return urls


class _NodesClient(KazooZookeeperClient):
    """A kazoo client with the node operations that only tests use, which the in-memory client has too."""

    async def children(self, path: str) -> list[str]:
        def children() -> list[str]:
            try:
                return self._kazoo.get_children(path)
            except NoNodeError:
                return []

        return await to_thread.run_sync(children)

    async def create(self, path: str, data: bytes = b"") -> None:
        def create() -> None:
            with contextlib.suppress(NodeExistsError):
                self._kazoo.create(path, data, makepath=True)

        await to_thread.run_sync(create)

    async def set(self, path: str, data: bytes) -> None:
        def set_() -> None:
            try:
                self._kazoo.set(path, data)
            except NoNodeError:
                self._kazoo.create(path, data, makepath=True)

        await to_thread.run_sync(set_)

    async def delete(self, path: str) -> None:
        def delete() -> None:
            with contextlib.suppress(NoNodeError):
                self._kazoo.delete(path)

        await to_thread.run_sync(delete)


@asynccontextmanager
async def _zk(address: str) -> AsyncIterator[Any]:
    """Yield a client of ``address`` with the node operations of `_NodesClient`, which disconnects on exit.

    With ``client=memory`` it is the in-memory client, in an application of its own.
    """
    url = URL.parse(address)
    if url.parameters.get("client") == "memory":
        async with ApplicationScope() as scope:
            yield await get_zookeeper_client(url.replace(attributes={APPLICATION_SCOPE: scope}))
        return

    async with _NodesClient(url) as client:
        yield client


async def _delete_tree(client: Any, path: str) -> None:
    """Delete the node at ``path`` and those under it, through a client that `_zk` yields."""
    for child in await client.children(path):
        await _delete_tree(client, f"{path}/{child}")
    await client.delete(path)


@pytest.fixture
def zk():
    return _zk


@pytest.fixture
def delete_tree():
    return _delete_tree
