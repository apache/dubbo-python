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

from .base import ConfigCenter

__all__ = ["NacosConfigCenter"]


class NacosConfigCenter(ConfigCenter):
    """A ``ConfigCenter`` that stores each entry as a Nacos configuration.

    The entry of ``key`` in ``group`` is the configuration whose data id is
    ``key`` in the Nacos group ``group``, in the namespace that the
    ``namespace`` URL parameter names. The client comes from
    ``get_nacos_config_client``, shared with the other users of an equal
    connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._client: nacos.NacosConfigClient | None = None

    async def get(self, key: str, *, group: str) -> str | None:
        client = self._connected()

        return await client.get(key, group)

    @asynccontextmanager
    async def watch(self, key: str, *, group: str) -> AsyncGenerator[AsyncIterator[str | None]]:
        client = self._connected()

        async with client.watch(key, group) as contents:
            yield contents

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await nacos.get_nacos_config_client(self.url)
        return self

    def _connected(self) -> nacos.NacosConfigClient:
        if self._client is None:
            raise RuntimeError("the configuration center is not connected")
        return self._client
