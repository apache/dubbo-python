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
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Self
from urllib.parse import quote_plus, unquote_plus, urlsplit

from dubbo.constants import CATEGORY_KEY, DEFAULT_ROOT, GROUP_KEY, INTERFACE_KEY, PROVIDERS_CATEGORY
from dubbo.transport import zookeeper
from dubbo.url import URL

from ..base import InterfaceRegistry

__all__ = ["ZookeeperInterfaceRegistry"]

_logger = logging.getLogger(__name__)


class ZookeeperInterfaceRegistry(InterfaceRegistry):
    """An ``InterfaceRegistry`` in ephemeral ZooKeeper nodes named by form-encoded URLs.

    A URL is the node ``/{group}/{interface}/{category}/{url}``, where
    ``group`` is the URL parameter and ``dubbo`` by default, and the
    interface and the URL, with its parameter values unescaped, are
    form-encoded: letters, digits and ``.-*_`` stay as they are, a space
    becomes ``+``, and every other byte of the UTF-8 text is escaped. The
    client comes from ``get_zookeeper_client``, shared with the other users
    of an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._root = "/" + url.parameters.get(GROUP_KEY, DEFAULT_ROOT).removeprefix("/")
        self._client: zookeeper.ZookeeperClient | None = None

    def register(self, url: URL) -> AbstractAsyncContextManager[None]:
        client = self._connected()

        return client.keep_ephemeral(self._path(url))

    @asynccontextmanager
    async def subscribe(
        self, interface: str, *, group: str | None, version: str | None
    ) -> AsyncGenerator[AsyncIterator[list[URL]]]:
        client = self._connected()
        parent = f"{self._root}/{_encode(interface)}/{PROVIDERS_CATEGORY}"

        async with client.watch_children(parent) as snapshots:
            yield (_urls(children, parent) async for children in snapshots)

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await zookeeper.get_zookeeper_client(self.url)
        return self

    def _path(self, url: URL) -> str:
        interface = url.parameters.get(INTERFACE_KEY) or url.path
        category = url.parameters.get(CATEGORY_KEY, PROVIDERS_CATEGORY)
        return f"{self._root}/{_encode(interface)}/{category}/{_encode(_full_string(url))}"

    def _connected(self) -> zookeeper.ZookeeperClient:
        if self._client is None:
            raise RuntimeError("the registry is not connected")
        return self._client


def _full_string(url: URL) -> str:
    """Return ``url`` with its user, password and parameter values unescaped, parameters sorted by key, as registry nodes hold it."""
    user = f"{url.userinfo}@" if url.userinfo else ""
    path = f"/{url.path}" if url.path else ""
    query = "&".join(f"{key}={value}" for key, value in sorted(url.parameters.items()))
    return f"{url.protocol}://{user}{url.address}{path}" + (f"?{query}" if query else "")


def _parse_full_string(text: str) -> URL:
    """Read a URL that ``_full_string`` returns, whose parameter values are not escaped.

    Raises:
        ValueError: The text is not such a URL.
    """
    address, _, query = text.partition("?")
    parts = urlsplit(address)
    if not parts.scheme:
        raise ValueError(f"URL needs a scheme: {text!r}")

    parameters = {}
    for pair in query.split("&"):
        key, _, value = pair.partition("=")
        if key:
            parameters[key] = value

    return URL(
        protocol=parts.scheme,
        username=parts.username,
        password=parts.password,
        host=parts.hostname,
        port=parts.port,
        path=parts.path.removeprefix("/"),
        parameters=parameters,
    )


def _encode(text: str) -> str:
    # Form encoding leaves only letters, digits and ".-*_" as they are.
    return quote_plus(text, safe="*").replace("~", "%7E")


def _urls(children: list[str], parent: str) -> list[URL]:
    urls = []
    for child in children:
        try:
            urls.append(_parse_full_string(unquote_plus(child, errors="strict")))
        except ValueError:
            # The name is left out: it is written by others and may hold a token or password.
            _logger.warning("Ignoring a node in %s, which holds no URL", parent)

    return urls
