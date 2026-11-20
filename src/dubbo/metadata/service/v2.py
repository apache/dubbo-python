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

"""MetadataServiceV2, version 2.0.0 of the MetadataService, which Triple carries in protobuf."""

from dubbo._proto.org.apache.dubbo.metadata.metadata_service_v2_dubbo import (
    MetadataServiceV2,
    MetadataServiceV2Servicer,
)
from dubbo._proto.org.apache.dubbo.metadata.metadata_service_v2_pb2 import (
    MetadataInfoV2,
    MetadataRequest,
    OpenAPIInfo,
    OpenAPIRequest,
    ServiceInfoV2,
)
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.client import proxy
from dubbo.rpc.invocation import Invoke

from ..info import MetadataInfo, ServiceInfo
from .server import MetadataStore

__all__ = ["MetadataRequest", "MetadataServiceV2", "MetadataServiceV2Server", "OpenAPIRequest", "read_metadata_info"]


class MetadataServiceV2Server(MetadataServiceV2Servicer):
    """Serves the metadata ``metadata`` holds; a revision it does not hold fails as ``NOT_FOUND``."""

    def __init__(self, metadata: MetadataStore) -> None:
        self._metadata = metadata

    async def get_metadata_info(self, request: MetadataRequest) -> MetadataInfoV2:
        metadata = self._metadata.get(request.revision)
        if metadata is None:
            raise RpcError(Status.NOT_FOUND, f"no metadata at revision {request.revision!r}")

        services = {key: _service_v2(service) for key, service in metadata.services.items()}
        return MetadataInfoV2(app=metadata.app, version=metadata.revision, services=services)

    async def get_open_api_info(self, request: OpenAPIRequest) -> OpenAPIInfo:
        raise RpcError(Status.UNIMPLEMENTED, "OpenAPI documents are not served")


async def read_metadata_info(invoke: Invoke, revision: str) -> MetadataInfo:
    """Return the metadata at ``revision`` of the MetadataServiceV2 that ``invoke`` calls."""
    message = await proxy(MetadataServiceV2, invoke).get_metadata_info(MetadataRequest(revision=revision))
    services = [
        ServiceInfo(
            name=service.name,
            group=service.group or None,
            version=service.version or None,
            protocol=service.protocol,
            port=service.port,
            path=service.path or service.name,
            params=dict(service.params),
        )
        for service in message.services.values()
    ]
    return MetadataInfo.from_services(message.app, services)


def _service_v2(service: ServiceInfo) -> ServiceInfoV2:
    return ServiceInfoV2(
        name=service.name,
        group=service.group or "",
        version=service.version or "",
        protocol=service.protocol,
        port=service.port,
        path=service.path,
        params=dict(service.params),
    )
