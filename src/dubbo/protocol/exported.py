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

"""How the services of an application are served on their protocols, through filters that override rules change."""

import logging
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager

import anyio
import attrs

from dubbo.config import DubboConfig
from dubbo.config.urls import service_registries
from dubbo.extension import ApplicationScope, ExtensionError
from dubbo.filter import chain_filters, get_service_filters
from dubbo.protocol import Exporter, get_protocol
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

__all__ = ["ExportedService", "export_services"]

_logger = logging.getLogger(__name__)


@attrs.define(frozen=True, kw_only=True)
class ExportedService:
    """A service served on one of its protocols, ready to be registered.

    Attributes:
        interface: Interface name of the service.
        definition: The contract of the service.
        url: The URL its exporter serves, with the port actually bound.
        reconfigure: What applies to how it serves the parameters that the
            override rules of providers change, all of them each time.
        registries: The URL of each registry to register the service with,
            unless it sets ``register`` to false.
    """

    interface: str
    definition: Service
    url: URL
    reconfigure: Callable[[Mapping[str, str]], None]
    registries: Sequence[URL]


@asynccontextmanager
async def export_services(
    config: DubboConfig, urls: Mapping[str, list[URL]], services: Mapping[str, Service], scope: ApplicationScope
) -> AsyncGenerator[list[ExportedService]]:
    """Serve each of ``services`` with its ``urls`` until the context exits.

    Each serves its calls through the filters its settings add and
    ``service.filter`` names, which follow the override rules that
    `dubbo.registry.provider.register_services` applies.
    """
    exporters: list[Exporter] = []
    try:
        exported = []
        for interface, service in services.items():
            registries = service_registries(config, interface, scope)
            for url in urls[interface]:
                protocol = await get_protocol(url.protocol, scope)
                # ty reads the attrs field `url` as leaving the property of `Invoker` abstract.
                invoker = _Reconfigurable(ServiceInvoker(url=url, service=service), url)  # ty: ignore[abstract-class-instantiation]
                exporter = await protocol.export(url, service, invoker)
                exporters.append(exporter)
                exported.append(
                    ExportedService(
                        interface=interface,
                        definition=service,
                        url=exporter.url,
                        reconfigure=invoker.reconfigure,
                        registries=registries,
                    )
                )

        yield exported
    finally:
        # The exporters close together, so that their running calls share one grace period.
        async with anyio.create_task_group() as task_group:
            for exporter in exporters:
                task_group.start_soon(exporter.aclose)


class _Reconfigurable(Invoker):
    """Serves the calls of a service through the filters of its URL with the parameters the override rules change."""

    def __init__(self, service: ServiceInvoker, url: URL) -> None:
        self._service = service
        self._url = url
        self._chain = chain_filters(service, get_service_filters(url))

    @property
    def url(self) -> URL:
        return self._url

    @property
    def available(self) -> bool:
        return self._service.available

    def reconfigure(self, changes: Mapping[str, str]) -> None:
        """Serve the calls from now on through the filters of the URL updated with ``changes``, every parameter the rules change.

        Calls already running finish through the filters they started with.
        Filters that the changed URL cannot create leave those before.
        """
        url = self._url.update_parameters(changes)
        try:
            self._chain = chain_filters(self._service, get_service_filters(url))
        except (ValueError, ExtensionError):
            _logger.warning(
                "Cannot apply the override rules of %s; its calls keep their filters",
                self._url.service_key,
                exc_info=True,
            )

    async def invoke(self, invocation: Invocation) -> Result:
        return await self._chain.invoke(invocation)

    async def aclose(self) -> None:
        await self._service.aclose()
