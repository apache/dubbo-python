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
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Self

from dubbo.extension import Resource, extension_point, extensions
from dubbo.url import URL

__all__ = ["ConfigCenter", "get_config_center"]


@extension_point("apache_dubbo.config_center")
class ConfigCenter(Resource, typing.Protocol):
    """Read and watch text entries stored by key and group in a configuration center.

    The implementation is named by the scheme of the configuration center URL
    and created with that URL, which carries the address, the query parameters
    and ``ConfigCenterConfig.parameters``, and ``timeout`` in milliseconds: the
    limit for each operation. It is installed under the entry point group
    ``apache_dubbo.config_center``, named by that scheme.

    Entering ``async with`` connects, and closing disconnects. The application
    opens one instance per URL, through `get_config_center`, reads its
    configuration at startup, and keeps it open while it runs, for the
    override and routing rules that watch it. Clients that other extensions of
    the application also use come from getters that share them through
    ``url.scope``, such as `get_zookeeper_client`: take them on entering and
    leave them open on closing, as the scope closes them.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    async def get(self, key: str, *, group: str) -> str | None:
        """Return the text under ``key`` in ``group``, or ``None`` if the entry does not exist.

        Raises:
            Exception: Any error of its client when the entry cannot be read;
                startup decides by ``check`` whether that fails it.
        """
        ...

    def watch(self, key: str, *, group: str) -> AbstractAsyncContextManager[AsyncIterator[str | None]]:
        """Watch the text under ``key`` in ``group`` until the context exits.

        The iterator yields the current text first, then the text after each
        change, with ``None`` while the entry does not exist. Each entry holds
        a complete document, so only the latest text matters: changes made
        while the consumer is busy may be skipped, but the latest is always
        yielded. The first text may fail, raising the error of the client;
        the rules that watch then subscribe again after a delay.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the configuration center."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the configuration center."""
        ...


async def get_config_center(url: URL) -> ConfigCenter:
    """Return the configuration center ``url`` names, the same instance for the same URL in its application.

    The application of ``url.scope`` connects it on first use and
    disconnects it when it stops.

    Raises:
        ExtensionError: No implementation has the scheme of ``url``.
        RuntimeError: ``url`` belongs to no running application.
    """
    scope = url.scope
    implementation = extensions.get(ConfigCenter, url.protocol)
    return await scope.share((implementation, url), lambda: implementation(url))
