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

import typing
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Self

import attrs

from dubbo.config import RegistryMode
from dubbo.constants import DEFAULT_REGISTRY_MODE, REGISTER_MODE_KEY
from dubbo.extension import Resource, extension_point, extensions
from dubbo.url import URL
from dubbo.utils import freeze_mapping

__all__ = [
    "InstanceRegistry",
    "InterfaceRegistry",
    "ServiceInstance",
    "get_instance_registry",
    "get_interface_registry",
    "registry_mode",
]


@extension_point("apache_dubbo.interface_registry")
class InterfaceRegistry(Resource, typing.Protocol):
    """Register service URLs by interface and watch those of providers.

    The implementation is installed under the entry point group
    ``apache_dubbo.interface_registry``, named by the scheme of the registry
    URL, such as ``zookeeper``, and created with that URL. Entering
    ``async with`` connects, and closing disconnects. The application opens
    one instance per URL, through `get_interface_registry`. Clients that other
    extensions of the application also use come from getters that share them
    through ``url.scope``, such as `get_zookeeper_client`: take them on
    entering and leave them open on closing, as the scope closes them.

    Each registration stays registered until its context exits, including
    while the connection to the registry is lost and found again.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    def register(self, url: URL) -> AbstractAsyncContextManager[None]:
        """Keep ``url`` registered under its ``interface`` parameter, or its path, and its ``category`` until the context exits.

        The category is ``providers`` when the URL has none; a consumer
        registers itself with ``consumers``. Entering registers the URL and
        exiting removes it; entering is all or nothing, so one that fails
        leaves nothing registered.
        """
        ...

    def subscribe(
        self, interface: str, *, group: str | None, version: str | None
    ) -> AbstractAsyncContextManager[AsyncIterator[list[URL]]]:
        """Watch the URLs of the providers of ``interface`` until the context exits.

        ``group`` and ``version`` are those the consumer wants: ``None`` for
        none, ``*`` for any, and for the group, several separated by commas.
        A registry that keeps the providers of each group and version apart
        uses them to find the providers; the URLs it yields may still
        include others, which the consumer leaves out.

        The iterator yields the current URLs first, then the URLs after each
        change. URLs the registry holds but that cannot be read are left out.
        Changes made while the consumer is busy may be skipped, but the latest
        is always yielded. Only the first URLs can fail, and their failure is
        raised as it is, not in an exception group: after them the
        iterator neither raises nor ends until the context exits, and keeps
        the last URLs while the registry is unreachable.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the registry."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the registry."""
        ...


@attrs.define(frozen=True, kw_only=True)
class ServiceInstance:
    """One running instance of an application, as an ``InstanceRegistry`` registers it.

    Attributes:
        app: Name of the application.
        host: Address consumers reach the instance at.
        port: Port of the instance's main protocol.
        metadata: What consumers need besides the address, such as the
            revision of the application's metadata.
    """

    app: str
    host: str
    port: int
    metadata: Mapping[str, str] = attrs.field(factory=dict, converter=freeze_mapping, hash=False)

    @property
    def id(self) -> str:
        """``host:port``, which tells the instances of one application apart."""
        return f"{self.host}:{self.port}"


@extension_point("apache_dubbo.instance_registry")
class InstanceRegistry(Resource, typing.Protocol):
    """Register the instances of applications and watch those of other applications.

    The implementation is installed under the entry point group
    ``apache_dubbo.instance_registry``, named by the scheme of the registry
    URL, such as ``zookeeper``, and created with that URL. Entering
    ``async with`` connects, and closing disconnects. The application opens
    one instance per URL, through `get_instance_registry`. Clients that other
    extensions of the application also use come from getters that share them
    through ``url.scope``, such as `get_zookeeper_client`: take them on
    entering and leave them open on closing, as the scope closes them.

    Each registration stays registered until its context exits, including
    while the connection to the registry is lost and found again.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    def register(self, instance: ServiceInstance) -> AbstractAsyncContextManager[None]:
        """Keep ``instance`` registered until the context exits.

        Entering registers the instance, replacing a registered one with the
        same application and id, and exiting removes it, unless a later
        registration has replaced it meanwhile. Entering is all or nothing,
        so one that fails leaves nothing of its own registered.
        """
        ...

    def subscribe(self, app: str) -> AbstractAsyncContextManager[AsyncIterator[list[ServiceInstance]]]:
        """Watch the instances of the application ``app`` until the context exits.

        The iterator yields the current instances first, then the instances
        after each change, including a change of an instance's metadata.
        Changes made while the consumer is busy may be skipped, but the latest
        is always yielded. Only the first instances can fail, and their failure is
        raised as it is, not in an exception group: after them the
        iterator neither raises nor ends until the context exits, and keeps
        the last instances while the registry is unreachable.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the registry."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the registry."""
        ...


async def get_interface_registry(url: URL) -> InterfaceRegistry:
    """Return the interface registry ``url`` names, the same instance for the same URL in its application.

    The application of ``url.scope`` connects it on first use and
    disconnects it when it stops.

    Raises:
        ExtensionError: No implementation has the scheme of ``url``.
        RuntimeError: ``url`` belongs to no running application.
    """
    scope = url.scope
    implementation = extensions.get(InterfaceRegistry, url.protocol)
    return await scope.share((implementation, url), lambda: implementation(url))


async def get_instance_registry(url: URL) -> InstanceRegistry:
    """Return the instance registry ``url`` names, the same instance for the same URL in its application.

    The application of ``url.scope`` connects it on first use and
    disconnects it when it stops.

    Raises:
        ExtensionError: No implementation has the scheme of ``url``.
        RuntimeError: ``url`` belongs to no running application.
    """
    scope = url.scope
    implementation = extensions.get(InstanceRegistry, url.protocol)
    return await scope.share((implementation, url), lambda: implementation(url))


def registry_mode(url: URL) -> RegistryMode:
    """Return how the registry of ``url`` registers and discovers services: its ``register-mode``, else ``all``.

    Raises:
        ValueError: ``register-mode`` names no mode.
    """
    return RegistryMode(url.get_parameter(REGISTER_MODE_KEY, RegistryMode, DEFAULT_REGISTRY_MODE))
