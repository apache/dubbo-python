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

from dubbo.constants import DEFAULT_ROOT, GROUP_KEY
from dubbo.transport import zookeeper
from dubbo.url import URL
from dubbo.utils.converters import comma_separated

from ..info import MetadataInfo
from .base import MetadataReport

__all__ = ["ZookeeperMetadataReport"]


class ZookeeperMetadataReport(MetadataReport):
    """A ``MetadataReport`` in persistent ZooKeeper nodes.

    Under ``/{group}``, where ``group`` is the URL parameter and ``dubbo`` by
    default, the applications that provide an interface are the
    comma-separated names in ``mapping/{interface}``, and the metadata of an
    application is the JSON in ``metadata/{app}/{revision}``. Both nodes are
    persistent. The client comes from ``get_zookeeper_client``, shared with
    the other users of an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._root = "/" + url.parameters.get(GROUP_KEY, DEFAULT_ROOT).removeprefix("/")
        self._client: zookeeper.ZookeeperClient | None = None

    async def publish_app_metadata(self, metadata: MetadataInfo) -> None:
        client = self._connected()

        content = metadata.to_json().encode()
        await client.update(self._metadata_path(metadata.app, metadata.revision), lambda data: data or content)

    async def get_app_metadata(self, app: str, revision: str) -> MetadataInfo | None:
        client = self._connected()

        data = await client.get(self._metadata_path(app, revision))
        return MetadataInfo.from_json(data.decode()) if data else None

    async def register_service_app_mapping(self, interface: str, app: str) -> None:
        client = self._connected()

        def add(data: bytes | None) -> bytes:
            text = (data or b"").decode()
            if app in _names(text):
                return data or b""
            return f"{text},{app}".encode() if text else app.encode()

        await client.update(self._mapping_path(interface), add)

    @asynccontextmanager
    async def subscribe_service_app_mapping(self, interface: str) -> AsyncGenerator[AsyncIterator[frozenset[str]]]:
        client = self._connected()

        async with client.watch(self._mapping_path(interface)) as values:
            yield (_readable_names(data or b"") async for data in values)

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await zookeeper.get_zookeeper_client(self.url)
        return self

    def _metadata_path(self, app: str, revision: str) -> str:
        return f"{self._root}/metadata/{app}/{revision}"

    def _mapping_path(self, interface: str) -> str:
        return f"{self._root}/mapping/{interface}"

    def _connected(self) -> zookeeper.ZookeeperClient:
        if self._client is None:
            raise RuntimeError("the metadata report is not connected")
        return self._client


def _names(text: str) -> frozenset[str]:
    return frozenset(comma_separated(text))


def _readable_names(data: bytes) -> frozenset[str]:
    # A name that is not UTF-8 is left out; the others are still read.
    return frozenset(name for name in _names(data.decode(errors="replace")) if "\ufffd" not in name)
