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

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Self

from dubbo.constants import DEFAULT_ROOT, NAMESPACE_KEY
from dubbo.transport import zookeeper
from dubbo.url import URL

from .base import ConfigCenter

__all__ = ["ZookeeperConfigCenter"]


class ZookeeperConfigCenter(ConfigCenter):
    """A ``ConfigCenter`` that stores each entry as the UTF-8 text of a ZooKeeper node.

    The node of ``key`` in ``group`` is ``/{namespace}/config/{group}/{key}``;
    the ``namespace`` URL parameter is ``dubbo`` by default. The client comes
    from ``get_zookeeper_client``, shared with the other users of an equal
    connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._root = f"/{url.parameters.get(NAMESPACE_KEY, DEFAULT_ROOT)}/config"
        self._client: zookeeper.ZookeeperClient | None = None

    async def get(self, key: str, *, group: str) -> str | None:
        client = self._connected()

        data = await client.get(self._path(key, group))
        return _text(data)

    @asynccontextmanager
    async def watch(self, key: str, *, group: str) -> AsyncGenerator[AsyncIterator[str | None]]:
        client = self._connected()

        async with client.watch(self._path(key, group)) as values:
            yield (_text(data) async for data in values)

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await zookeeper.get_zookeeper_client(self.url)
        return self

    def _path(self, key: str, group: str) -> str:
        return f"{self._root}/{group}/{key}"

    def _connected(self) -> zookeeper.ZookeeperClient:
        if self._client is None:
            raise RuntimeError("the configuration center is not connected")
        return self._client


def _text(data: bytes | None) -> str | None:
    return None if data is None else data.decode()
