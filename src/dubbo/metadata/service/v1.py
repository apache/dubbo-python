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

"""MetadataService 1.0.0, which carries the metadata of an instance as Java objects over the protocols that call Java methods."""

import typing

import attrs
import hessian2

from dubbo.rpc.client import proxy
from dubbo.rpc.definition import method, service
from dubbo.rpc.invocation import Invoke

from ..info import MetadataInfo, ServiceInfo
from ..instance import METADATA_SERVICE_V1, METADATA_SERVICE_V1_VERSION
from .server import MetadataStore

__all__ = [
    "JavaMetadataInfo",
    "JavaServiceInfo",
    "MetadataServiceV1",
    "MetadataServiceV1Server",
    "read_metadata_info",
]


@hessian2.java_class("org.apache.dubbo.metadata.MetadataInfo$ServiceInfo")
@attrs.define(frozen=True, kw_only=True)
class JavaServiceInfo:
    """A service as ``org.apache.dubbo.metadata.MetadataInfo$ServiceInfo`` carries it; see `ServiceInfo`."""

    name: str | None = None
    group: str | None = None
    version: str | None = None
    protocol: str | None = None
    port: int = -1
    path: str | None = None
    params: dict[str, str] | None = None


@hessian2.java_class("org.apache.dubbo.metadata.MetadataInfo")
@attrs.define(frozen=True, kw_only=True)
class JavaMetadataInfo:
    """The metadata of an application as ``org.apache.dubbo.metadata.MetadataInfo`` carries it; see `MetadataInfo`."""

    app: str | None = None
    revision: str | None = None
    services: dict[str, JavaServiceInfo] | None = None


@service(METADATA_SERVICE_V1)
class MetadataServiceV1(typing.Protocol):
    """The MetadataService of version 1.0.0, without the methods about URLs or listeners."""

    @method("serviceName")
    async def service_name(self) -> str:
        """Return the name of the application."""
        ...

    @method("version")
    async def version(self) -> str:
        """Return the version of the MetadataService, ``1.0.0``."""
        ...

    @method("getServiceDefinition")
    async def get_service_definition(self, service_key: str) -> str:
        """Return the definition of the service of ``service_key``, which is not served: always an empty text."""
        ...

    @method("getMetadataInfo")
    async def get_metadata_info(self, revision: str) -> JavaMetadataInfo | None:
        """Return the metadata at ``revision``, or ``None`` if it is not served."""
        ...

    @method("getMetadataInfos")
    async def get_metadata_infos(self) -> list[JavaMetadataInfo]:
        """Return the metadata of each revision served."""
        ...


class MetadataServiceV1Server(MetadataServiceV1):
    """Serves the metadata ``metadata`` holds for the application ``app``; a revision it does not hold is answered with ``None``."""

    def __init__(self, metadata: MetadataStore, app: str) -> None:
        self._metadata = metadata
        self._app = app

    async def service_name(self) -> str:
        return self._app

    async def version(self) -> str:
        return METADATA_SERVICE_V1_VERSION

    async def get_service_definition(self, service_key: str) -> str:
        return ""

    async def get_metadata_info(self, revision: str) -> JavaMetadataInfo | None:
        metadata = self._metadata.get(revision)
        return None if metadata is None else _metadata_v1(metadata)

    async def get_metadata_infos(self) -> list[JavaMetadataInfo]:
        return [_metadata_v1(metadata) for metadata in self._metadata.values()]


async def read_metadata_info(invoke: Invoke, revision: str) -> MetadataInfo | None:
    """Return the metadata at ``revision`` of the MetadataService that ``invoke`` calls, or ``None`` if it serves none.

    Raises:
        ValueError: The metadata names no application, or a service without
            its name or protocol.
    """
    message = await proxy(MetadataServiceV1, invoke).get_metadata_info(revision)
    if message is None:
        return None
    if not message.app:
        raise ValueError("the metadata names no application")

    services = []
    for java in (message.services or {}).values():
        if not java.name or not java.protocol:
            raise ValueError(f"the metadata has a service without its name or protocol: {java}")
        services.append(
            ServiceInfo(
                name=java.name,
                group=java.group or None,
                version=java.version or None,
                protocol=java.protocol,
                port=java.port,
                path=java.path or java.name,
                params=java.params or {},
            )
        )
    return MetadataInfo.from_services(message.app, services)


def _metadata_v1(metadata: MetadataInfo) -> JavaMetadataInfo:
    services = {key: _service_v1(service) for key, service in metadata.services.items()}
    return JavaMetadataInfo(app=metadata.app, revision=metadata.revision, services=services)


def _service_v1(service: ServiceInfo) -> JavaServiceInfo:
    return JavaServiceInfo(
        name=service.name,
        group=service.group,
        version=service.version,
        protocol=service.protocol,
        port=service.port,
        path=service.path,
        params=dict(service.params),
    )
