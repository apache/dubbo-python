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
from typing import Self, cast

from dubbo.extension import Resource, extension_point, extensions
from dubbo.url import METADATA_REPORT_URL, URL

from ..info import MetadataInfo

__all__ = ["MetadataReport", "get_metadata_report"]


@extension_point("apache_dubbo.metadata_report")
class MetadataReport(Resource, typing.Protocol):
    """Store what consumers of application-level discovery read besides the instances.

    That is the applications that provide each interface, and the metadata of
    applications whose instances do not serve it themselves. The registry
    stores both unless the application sets a metadata report apart, so the
    implementation is installed under the entry point group
    ``apache_dubbo.metadata_report``, named by the scheme of the URL of
    either, such as ``zookeeper``, and created with that URL. Entering
    ``async with`` connects, and closing disconnects. The application opens
    one instance per URL, through `get_metadata_report`. Clients that other
    extensions of the application also use come from getters that share them
    through ``url.scope``, such as `get_zookeeper_client`: take them on
    entering and leave them open on closing, as the scope closes them.

    A provider calls `register_service_app_mapping` as it first registers
    its instance, and `publish_app_metadata` when its metadata is
    ``remote``. A consumer calls `subscribe_service_app_mapping` for the
    interfaces whose applications ``provided-by`` does not name, and
    `get_app_metadata` for the instances whose metadata is ``remote``.
    Metadata is stored as the text of `MetadataInfo.to_json`, and read with
    `MetadataInfo.from_json`. Operations raise the error of the client,
    such as ``ZookeeperError``, when the store cannot be reached.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    async def publish_app_metadata(self, metadata: MetadataInfo) -> None:
        """Store ``metadata`` under its application and revision, unless it is stored already."""
        ...

    async def get_app_metadata(self, app: str, revision: str) -> MetadataInfo | None:
        """Return the metadata stored for ``app`` at ``revision``, or ``None`` if there is none.

        Raises:
            ValueError: The stored metadata cannot be read.
        """
        ...

    async def register_service_app_mapping(self, interface: str, app: str) -> None:
        """Record that ``app`` provides ``interface``, keeping the other applications recorded for it."""
        ...

    def subscribe_service_app_mapping(
        self, interface: str
    ) -> AbstractAsyncContextManager[AsyncIterator[frozenset[str]]]:
        """Watch the applications that provide ``interface`` until the context exits.

        The iterator yields the current names first, then the names after
        each change. Changes made while the consumer is busy may be skipped,
        but the latest is always yielded. Only the first names can fail, and
        their failure is raised as it is, not in an exception group: after
        them the iterator neither raises nor ends until the context exits,
        and keeps the last names while the store is unreachable.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from where the metadata is stored."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to where the metadata is stored."""
        ...


async def get_metadata_report(registry: URL) -> MetadataReport:
    """Return the metadata report of ``registry``, the same instance for the same URL in its application.

    It is the one the attribute ``METADATA_REPORT_URL`` of ``registry`` names,
    else the registry itself. The application of its scope connects it on
    first use and disconnects it when it stops.

    Raises:
        ExtensionError: No implementation has the scheme of its URL.
        RuntimeError: Its URL belongs to no running application.
    """
    url = cast(URL, registry.attributes.get(METADATA_REPORT_URL, registry))
    scope = url.scope
    implementation = extensions.get(MetadataReport, url.protocol)
    return await scope.share((implementation, url), lambda: implementation(url))
