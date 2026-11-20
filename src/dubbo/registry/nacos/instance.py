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
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Self

from dubbo.constants import GROUP_KEY
from dubbo.transport import nacos
from dubbo.url import URL

from ..base import InstanceRegistry, ServiceInstance

__all__ = ["NacosInstanceRegistry"]

_NACOS_GROUP_KEY = "nacos.group"


class NacosInstanceRegistry(InstanceRegistry):
    """An ``InstanceRegistry`` in Nacos services named after the applications.

    An instance of an application is an instance of the service named after
    the application, carrying the instance's metadata, in the Nacos group
    that the ``nacos.group`` URL parameter names, else ``group``, else
    ``DEFAULT_GROUP``. The client comes from ``get_nacos_naming_client``, shared
    with the other users of an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        parameters = url.parameters
        self._group = parameters.get(_NACOS_GROUP_KEY) or parameters.get(GROUP_KEY, nacos.DEFAULT_GROUP)
        self._client: nacos.NacosNamingClient | None = None

    def register(self, instance: ServiceInstance) -> AbstractAsyncContextManager[None]:
        client = self._connected()

        return client.keep_registered(instance.app, self._group, _nacos_instance(instance))

    @asynccontextmanager
    async def subscribe(self, app: str) -> AsyncGenerator[AsyncIterator[list[ServiceInstance]]]:
        client = self._connected()

        async with client.watch(app, self._group) as snapshots:
            yield (
                [
                    ServiceInstance(app=app, host=instance.host, port=instance.port, metadata=instance.metadata)
                    for instance in instances
                ]
                async for instances in snapshots
            )

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await nacos.get_nacos_naming_client(self.url)
        return self

    def _connected(self) -> nacos.NacosNamingClient:
        if self._client is None:
            raise RuntimeError("the registry is not connected")
        return self._client


def _nacos_instance(instance: ServiceInstance) -> nacos.NacosInstance:
    return nacos.NacosInstance(host=instance.host, port=instance.port, metadata=instance.metadata)
