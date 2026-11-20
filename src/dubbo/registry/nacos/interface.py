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

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Self

from dubbo.constants import (
    CATEGORY_KEY,
    CONSUMERS_CATEGORY,
    GROUP_KEY,
    INTERFACE_KEY,
    PATH_KEY,
    PROVIDERS_CATEGORY,
    VERSION_KEY,
)
from dubbo.transport import nacos
from dubbo.url import URL
from dubbo.utils import Latest, create_background_task_group
from dubbo.utils.converters import boolean

from ..base import InterfaceRegistry

__all__ = ["NacosInterfaceRegistry"]

_logger = logging.getLogger(__name__)

_PROTOCOL_KEY = "protocol"
_REGISTER_CONSUMER_URL_KEY = "register-consumer-url"
_ANY = "*"


class NacosInterfaceRegistry(InterfaceRegistry):
    """An ``InterfaceRegistry`` in Nacos services named by category, interface, version and group.

    A URL is an instance of the service
    ``{category}:{interface}:{version}:{group}``, with an empty segment for a
    missing version or group, in the Nacos group that the ``group`` URL
    parameter names, ``DEFAULT_GROUP`` by default. The instance carries the
    URL's parameters, with its ``category``, ``protocol`` and ``path``, at
    port 0 when the URL has none, as a consumer URL. Consumers register
    only when the ``register-consumer-url`` parameter is true. The client
    comes from ``get_nacos_naming_client``, shared with the other users of
    an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._group = url.parameters.get(GROUP_KEY, nacos.DEFAULT_GROUP)
        self._register_consumers = url.get_parameter(_REGISTER_CONSUMER_URL_KEY, boolean, False)
        self._client: nacos.NacosNamingClient | None = None

    @asynccontextmanager
    async def register(self, url: URL) -> AsyncGenerator[None]:
        client = self._connected()

        if not self._registers(url):
            yield
            return

        async with client.keep_registered(_service(url), self._group, _instance(url)):
            yield

    @asynccontextmanager
    async def subscribe(
        self, interface: str, *, group: str | None, version: str | None
    ) -> AsyncGenerator[AsyncIterator[list[URL]]]:
        client = self._connected()
        # shortcut: "*" would need the services of the group listed and polled; add it when someone needs it.
        if group == _ANY or version == _ANY:
            raise ValueError(f"a Nacos registry cannot watch any group or version of {interface}: name them")

        services = [f"{PROVIDERS_CATEGORY}:{interface}:{version or ''}:{name}" for name in (group or "").split(",")]
        latest: Latest[list[URL]] = Latest()
        urls: dict[str, list[URL]] = {}

        async def receive(service: str, snapshots: AsyncIterator[list[nacos.NacosInstance]]) -> None:
            async for instances in snapshots:
                urls[service] = _urls(instances, service)
                if len(urls) == len(services):
                    latest.publish([url for each in services for url in urls[each]])

        async with AsyncExitStack() as stack, create_background_task_group() as task_group:
            for service in services:
                snapshots = await stack.enter_async_context(client.watch(service, self._group))
                task_group.start_soon(receive, service, snapshots)
            yield aiter(latest)
            task_group.cancel_scope.cancel()

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await nacos.get_nacos_naming_client(self.url)
        return self

    def _registers(self, url: URL) -> bool:
        return url.parameters.get(CATEGORY_KEY, PROVIDERS_CATEGORY) != CONSUMERS_CATEGORY or self._register_consumers

    def _connected(self) -> nacos.NacosNamingClient:
        if self._client is None:
            raise RuntimeError("the registry is not connected")
        return self._client


def _service(url: URL) -> str:
    parameters = url.parameters
    interface = parameters.get(INTERFACE_KEY) or url.path
    category = parameters.get(CATEGORY_KEY, PROVIDERS_CATEGORY)
    return f"{category}:{interface}:{parameters.get(VERSION_KEY, '')}:{parameters.get(GROUP_KEY, '')}"


def _instance(url: URL) -> nacos.NacosInstance:
    if url.host is None:
        raise ValueError(f"a URL registered in Nacos needs a host: {url}")

    metadata = {
        **url.parameters,
        CATEGORY_KEY: url.parameters.get(CATEGORY_KEY, PROVIDERS_CATEGORY),
        _PROTOCOL_KEY: url.protocol,
        PATH_KEY: url.path,
    }
    return nacos.NacosInstance(host=url.host, port=url.port or 0, metadata=metadata)


def _urls(instances: list[nacos.NacosInstance], service: str) -> list[URL]:
    urls = []
    for instance in instances:
        parameters = dict(instance.metadata)
        protocol = parameters.pop(_PROTOCOL_KEY, None)
        if not protocol:
            _logger.warning(
                "Ignoring the instance %s:%d of %s, which names no protocol", instance.host, instance.port, service
            )
            continue
        path = parameters.pop(PATH_KEY, "")
        try:
            url = URL(protocol=protocol, host=instance.host, port=instance.port, path=path, parameters=parameters)
        except ValueError:
            _logger.warning(
                "Ignoring the instance %s:%d of %s, which holds no valid URL", instance.host, instance.port, service
            )
            continue
        urls.append(url)

    return urls
