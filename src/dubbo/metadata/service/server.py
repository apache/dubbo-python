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

"""How an instance serves the metadata of its application through its MetadataService."""

from collections.abc import Collection, Mapping
from contextlib import AsyncExitStack

from dubbo.config import ConfigError
from dubbo.constants import GROUP_KEY, SERIALIZATION_KEY, VERSION_KEY
from dubbo.protocol import get_protocol
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

from ..info import MetadataInfo
from ..instance import (
    METADATA_SERVICE_V1,
    METADATA_SERVICE_V1_SERIALIZATION,
    METADATA_SERVICE_V1_VERSION,
    METADATA_SERVICE_V2,
    METADATA_SERVICE_V2_VERSION,
)

__all__ = ["LocalMetadata", "MetadataStore"]


class MetadataStore:
    """Holds the metadata of the application by revision, which each version of the MetadataService serves."""

    def __init__(self) -> None:
        self._metadata: dict[str, MetadataInfo] = {}

    def add(self, metadata: MetadataInfo) -> None:
        """Serve ``metadata`` under its revision."""
        self._metadata[metadata.revision] = metadata

    def retain(self, revisions: Collection[str]) -> None:
        """Stop serving the metadata of revisions other than ``revisions``."""
        self._metadata = {revision: info for revision, info in self._metadata.items() if revision in revisions}

    def get(self, revision: str) -> MetadataInfo | None:
        """Return the metadata served at ``revision``, if any."""
        return self._metadata.get(revision)

    def values(self) -> tuple[MetadataInfo, ...]:
        """Return the metadata of each revision served, in the order they were added."""
        return tuple(self._metadata.values())


class LocalMetadata:
    """Serves the metadata of the application through its MetadataService, exported when it first serves a revision.

    ``urls`` holds the URL a service of the framework is served with on each
    protocol of the application, by name, and ``stack`` closes the export.
    Over tri, MetadataServiceV2 is served, and also
    the MetadataService 1.0.0 in it, for consumers that know only that one;
    without tri, the MetadataService 1.0.0 is served over dubbo.
    """

    def __init__(self, urls: Mapping[str, URL], stack: AsyncExitStack) -> None:
        self._urls = urls
        self._stack = stack
        self._metadata = MetadataStore()
        self._served: tuple[URL, ...] = ()

    @property
    def urls(self) -> tuple[URL, ...]:
        """The URLs the MetadataService is served with, each port the one bound, once it serves.

        The first is the one to publish; a consumer that knows the `version`
        served turns to it instead.
        """
        return self._served

    @property
    def version(self) -> str | None:
        """The latest version of the MetadataService served, once it serves."""
        if not self._served:
            return None
        if any(url.path == METADATA_SERVICE_V2 for url in self._served):
            return METADATA_SERVICE_V2_VERSION
        return METADATA_SERVICE_V1_VERSION

    async def serve(self, info: MetadataInfo) -> URL:
        """Serve ``info`` and return the URL the MetadataService is served with, its port the one bound.

        Raises:
            ConfigError: The application serves neither over tri nor over dubbo.
        """
        if not self._served:
            self._served = await self._export(info.app)

        self._metadata.add(info)
        return self._served[0]

    def retain(self, revisions: Collection[str]) -> None:
        """Stop serving the metadata of revisions other than ``revisions``."""
        self._metadata.retain(revisions)

    async def _export(self, app: str) -> tuple[URL, ...]:
        """Export the MetadataService and return the URLs it is served with, the one to publish first."""
        if "tri" in self._urls:
            from .v2 import MetadataServiceV2Server

            tri = self._urls["tri"]
            v2 = await self._export_one(
                tri.replace(path=METADATA_SERVICE_V2),
                METADATA_SERVICE_V2_VERSION,
                MetadataServiceV2Server(self._metadata),
                app,
            )
            from .v1 import MetadataServiceV1Server

            v1 = await self._export_one(
                tri.replace(path=METADATA_SERVICE_V1).update_parameters(
                    {SERIALIZATION_KEY: METADATA_SERVICE_V1_SERIALIZATION}
                ),
                METADATA_SERVICE_V1_VERSION,
                MetadataServiceV1Server(self._metadata, app),
                app,
            )
            return v1, v2

        if "dubbo" in self._urls:
            from .v1 import MetadataServiceV1Server

            v1 = await self._export_one(
                self._urls["dubbo"].replace(path=METADATA_SERVICE_V1),
                METADATA_SERVICE_V1_VERSION,
                MetadataServiceV1Server(self._metadata, app),
                app,
            )
            return (v1,)

        raise ConfigError(
            "local metadata is served over tri or dubbo, which no service uses; "
            "set application.metadata_type to remote, or serve a service over tri or dubbo"
        )

    async def _export_one(self, url: URL, version: str, implementation: object, app: str) -> URL:
        url = url.update_parameters({GROUP_KEY: app, VERSION_KEY: version})
        invoker = ServiceInvoker.from_implementation(implementation, url)
        exporter = await (await get_protocol(url.protocol, url.scope)).export(url, invoker.service, invoker)
        self._stack.push_async_callback(exporter.aclose)
        return exporter.url
