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

from dubbo.transport import nacos
from dubbo.url import URL
from dubbo.utils.converters import comma_separated

from ..info import MetadataInfo
from .base import MetadataReport

__all__ = ["NacosMetadataReport"]

_MAPPING_GROUP = "mapping"


class NacosMetadataReport(MetadataReport):
    """A ``MetadataReport`` in Nacos configurations.

    The applications that provide an interface are the comma-separated
    names in the configuration whose data id is the interface, in the group
    ``mapping``. The metadata of an application is the JSON in the
    configuration whose data id is the application, in the group named
    after the revision. The client comes from ``get_nacos_config_client``, shared
    with the other users of an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._client: nacos.NacosConfigClient | None = None

    async def publish_app_metadata(self, metadata: MetadataInfo) -> None:
        client = self._connected()

        content = metadata.to_json()
        await client.update(metadata.app, metadata.revision, lambda current: current or content)

    async def get_app_metadata(self, app: str, revision: str) -> MetadataInfo | None:
        client = self._connected()

        content = await client.get(app, revision)
        return MetadataInfo.from_json(content) if content else None

    async def register_service_app_mapping(self, interface: str, app: str) -> None:
        client = self._connected()

        def add(current: str | None) -> str:
            if not current:
                return app
            return current if app in comma_separated(current) else f"{current},{app}"

        await client.update(interface, _MAPPING_GROUP, add)

    @asynccontextmanager
    async def subscribe_service_app_mapping(self, interface: str) -> AsyncGenerator[AsyncIterator[frozenset[str]]]:
        client = self._connected()

        async with client.watch(interface, _MAPPING_GROUP) as contents:
            yield (frozenset(comma_separated(content or "")) async for content in contents)

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await nacos.get_nacos_config_client(self.url)
        return self

    def _connected(self) -> nacos.NacosConfigClient:
        if self._client is None:
            raise RuntimeError("the metadata report is not connected")
        return self._client
