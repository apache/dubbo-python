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
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Self, TypeVar

import attrs

from dubbo.constants import ACCESS_KEY_KEY, BACKUP_KEY, CLIENT_KEY, NAMESPACE_KEY, SECRET_KEY_KEY
from dubbo.extension import Resource, extension_point, extensions
from dubbo.url import URL
from dubbo.utils import freeze_mapping

__all__ = [
    "DEFAULT_GROUP",
    "NacosConfigClient",
    "NacosInstance",
    "NacosNamingClient",
    "get_nacos_config_client",
    "get_nacos_naming_client",
]

C = TypeVar("C", bound=Resource)

DEFAULT_GROUP = "DEFAULT_GROUP"  # The group of a service or configuration that names none, as Nacos has it.


@attrs.define(frozen=True, kw_only=True)
class NacosInstance:
    """One instance of a Nacos service.

    Attributes:
        host: Address of the instance.
        port: Port of the instance.
        metadata: Text the instance carries, such as the parameters of a URL.
    """

    host: str
    port: int
    metadata: Mapping[str, str] = attrs.field(factory=dict, converter=freeze_mapping, hash=False)


@extension_point("apache_dubbo.transport.nacos.naming", default="sdk")
class NacosNamingClient(Resource, typing.Protocol):
    """Register and watch the instances of services in one Nacos namespace.

    The implementation is created with a registry URL and reads only its
    connection part: the host and port, 8848 if absent, then the
    ``host[:port]`` entries of ``backup``; ``namespace``, the public
    namespace if absent; the user and password, or ``accessKey`` and
    ``secretKey``; and ``timeout`` for each operation, in milliseconds.
    Service names and groups are stored with ``$`` as ``___``.

    Entering ``async with`` connects, and closing disconnects, which removes
    the instances the client registered. Operations fail with ``NacosError``
    when the server is unreachable, times out or refuses them.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    def keep_registered(self, service: str, group: str, instance: NacosInstance) -> AbstractAsyncContextManager[None]:
        """Keep ``instance`` of ``service`` in ``group`` registered until the context exits.

        Entering registers the instance, replacing one at the same host and
        port, and exiting removes it, unless a later keeper at the address
        has replaced it meanwhile. The instance is ephemeral: it stays
        registered while the client is open, including after the connection
        is lost and found again. Entering is all or nothing: one that fails
        leaves registered what was before, as far as the server allows. An
        exit that is cancelled leaves the instance to the connection, which
        removes it as the client closes.
        """
        ...

    def watch(self, service: str, group: str) -> AbstractAsyncContextManager[AsyncIterator[list[NacosInstance]]]:
        """Watch the healthy, enabled instances of ``service`` in ``group`` until the context exits.

        The iterator yields the current instances first, then the instances
        after each change, including when none are left. Changes made while
        the consumer is busy may be skipped, but the latest is always
        yielded. Only entering can fail, with ``NacosError``: after it the
        iterator neither raises nor ends until the context exits.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the server."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the server."""
        ...


@extension_point("apache_dubbo.transport.nacos.config", default="sdk")
class NacosConfigClient(Resource, typing.Protocol):
    """Read, write and watch the configurations in one Nacos namespace.

    The implementation is created with a configuration center or metadata
    report URL and reads only its connection part, as `NacosNamingClient`
    does. Data ids and groups are stored with ``$`` as ``___`` and ``/`` as
    ``-``.

    Entering ``async with`` connects, and closing disconnects. Operations
    fail with ``NacosError`` when the server is unreachable, times out or
    refuses them.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    async def get(self, data_id: str, group: str) -> str | None:
        """Return the content of ``data_id`` in ``group``, or ``None`` if it does not exist."""
        ...

    async def update(self, data_id: str, group: str, change: Callable[[str | None], str]) -> None:
        """Replace the content of ``data_id`` in ``group`` with ``change`` of its content.

        ``change`` receives ``None`` while the configuration does not exist.
        When another client writes it in between, ``change`` runs again on
        the new content. Content that ``change`` returns unchanged is not
        written.
        """
        ...

    def watch(self, data_id: str, group: str) -> AbstractAsyncContextManager[AsyncIterator[str | None]]:
        """Watch the content of ``data_id`` in ``group`` until the context exits.

        The iterator yields the current content first, then the content after
        each change, with ``None`` while it does not exist. Changes made while
        the consumer is busy may be skipped, but the latest is always yielded.
        Only entering can fail, with ``NacosError``: after it the iterator
        neither raises nor ends until the context exits.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the server."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the server."""
        ...


async def get_nacos_naming_client(url: URL) -> NacosNamingClient:
    """Return the naming client of the Nacos namespace ``url`` names, the same for the same connection in its application.

    The ``client`` parameter names the implementation, ``sdk`` if absent,
    installed with ``apache-dubbo[nacos]``. The application of
    ``url.scope`` connects it on first use and disconnects it when it stops.
    URLs that differ only in ``timeout`` share it, with the ``timeout`` of
    the first.

    Raises:
        ValueError: The URL has no host, or ``timeout`` is not positive
            whole milliseconds.
        ExtensionError: No implementation has the name in ``client``.
        NacosError: The server cannot be reached.
        RuntimeError: ``url`` belongs to no running application.
    """
    return await _share(NacosNamingClient, url)


async def get_nacos_config_client(url: URL) -> NacosConfigClient:
    """Return the configuration client of the Nacos namespace ``url`` names, the same for the same connection in its application.

    The ``client`` parameter names the implementation, ``sdk`` if absent,
    installed with ``apache-dubbo[nacos]``. The application of
    ``url.scope`` connects it on first use and disconnects it when it stops.
    URLs that differ only in ``timeout`` share it, with the ``timeout`` of
    the first.

    Raises:
        ValueError: The URL has no host, or ``timeout`` is not positive
            whole milliseconds.
        ExtensionError: No implementation has the name in ``client``.
        NacosError: The server cannot be reached.
        RuntimeError: ``url`` belongs to no running application.
    """
    return await _share(NacosConfigClient, url)


async def _share(point: type[C], url: URL) -> C:
    if url.host is None:
        raise ValueError(f"a Nacos client needs a host: {url}")

    implementation: Any = extensions.get(point, url.parameters.get(CLIENT_KEY))
    parameters = url.parameters
    key = (
        implementation,
        url.host,
        url.port,
        parameters.get(BACKUP_KEY),
        parameters.get(NAMESPACE_KEY),
        url.username,
        url.password,
        parameters.get(ACCESS_KEY_KEY),
        parameters.get(SECRET_KEY_KEY),
    )
    return await url.scope.share(key, lambda: implementation(url))
