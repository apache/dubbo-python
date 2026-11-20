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

"""The metadata an application instance registers, which locates the metadata of its services, and those services' URLs."""

import json
from collections.abc import Mapping
from typing import Self

import attrs

from dubbo.config import MetadataType
from dubbo.constants import (
    ENDPOINTS_KEY,
    GROUP_KEY,
    METADATA_REVISION_KEY,
    METADATA_SERVICE_URL_PARAMS_KEY,
    METADATA_SERVICE_VERSION_KEY,
    METADATA_STORAGE_TYPE_KEY,
    SERIALIZATION_KEY,
    VERSION_KEY,
)
from dubbo.url import URL

from .info import EMPTY_REVISION, MetadataInfo
from .report import MetadataReport

__all__ = [
    "METADATA_SERVICE_V1",
    "METADATA_SERVICE_V1_SERIALIZATION",
    "METADATA_SERVICE_V1_VERSION",
    "METADATA_SERVICE_V2",
    "METADATA_SERVICE_V2_VERSION",
    "InstanceMetadata",
    "instance_metadata",
    "read_metadata",
]

# The interface and the version of each MetadataService an instance may serve; its group is the application name.
METADATA_SERVICE_V1 = "org.apache.dubbo.metadata.MetadataService"
METADATA_SERVICE_V1_VERSION = "1.0.0"
METADATA_SERVICE_V2 = "org.apache.dubbo.metadata.MetadataServiceV2"
METADATA_SERVICE_V2_VERSION = "2.0.0"
# The format the MetadataService 1.0.0 carries its values in, over any protocol.
METADATA_SERVICE_V1_SERIALIZATION = "hessian2"


def instance_metadata(
    info: MetadataInfo,
    storage: MetadataType,
    urls: list[URL],
    metadata_service: Mapping[str, str] | None,
    metadata_version: str | None,
) -> dict[str, str]:
    """Return the metadata an instance serving ``urls`` registers for ``info``, stored as ``storage`` says.

    ``metadata_service`` holds the URL parameters of the MetadataService the
    instance publishes, among them its ``version``, ``protocol`` and
    ``port``, and ``metadata_version`` the latest version it serves, which a
    consumer that knows it calls instead; both are ``None`` when the
    instance serves none.
    """
    ports = {url.protocol: url.port for url in urls}
    values = {
        METADATA_REVISION_KEY: info.revision,
        METADATA_STORAGE_TYPE_KEY: str(storage),
        ENDPOINTS_KEY: _json([{"port": port, "protocol": protocol} for protocol, port in ports.items()]),
    }
    if metadata_service is not None:
        values[METADATA_SERVICE_URL_PARAMS_KEY] = _json(dict(metadata_service))
        values[METADATA_SERVICE_VERSION_KEY] = metadata_version or metadata_service[VERSION_KEY]

    return values


@attrs.define(frozen=True, kw_only=True)
class InstanceMetadata:
    """What the metadata of a registered instance tells about its services.

    Attributes:
        host: Host of the instance.
        port: Port of the instance.
        revision: Revision of the metadata of its services.
        storage: Where the metadata of its services is read.
        endpoints: The port of each protocol it serves.
        metadata_service: Where its MetadataService is called, with the
            interface and the version of the MetadataService, if it serves
            one: MetadataServiceV2 over tri when it says it serves 2.0.0,
            else the MetadataService 1.0.0 in hessian2 over the protocol it
            names.
    """

    host: str
    port: int
    revision: str
    storage: MetadataType
    endpoints: Mapping[str, int]
    metadata_service: URL | None

    @classmethod
    def from_metadata(cls, host: str, port: int, metadata: Mapping[str, str]) -> Self | None:
        """Read the ``metadata`` of the instance at ``host`` and ``port``, or return ``None`` if it serves nothing.

        Raises:
            ValueError: The metadata cannot be read.
        """
        revision = metadata.get(METADATA_REVISION_KEY)
        if not revision or revision == EMPTY_REVISION:
            return None

        try:
            storage = MetadataType(metadata.get(METADATA_STORAGE_TYPE_KEY) or MetadataType.LOCAL)
            endpoints = _endpoints(metadata.get(ENDPOINTS_KEY))
            service = _metadata_service(host, port, metadata) if storage is MetadataType.LOCAL else None
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"the metadata of the instance {host}:{port} cannot be read: {error}") from None

        return cls(
            host=host, port=port, revision=revision, storage=storage, endpoints=endpoints, metadata_service=service
        )

    def service_urls(self, info: MetadataInfo) -> list[URL]:
        """Return the URL of each service ``info`` lists, at this instance."""
        urls = []
        for service in info.services.values():
            port = service.port if service.port > 0 else self.endpoints.get(service.protocol, self.port)
            identity = {GROUP_KEY: service.group, VERSION_KEY: service.version}
            urls.append(
                URL(
                    protocol=service.protocol,
                    host=self.host,
                    port=port,
                    path=service.path,
                    parameters={**service.params, **{key: value for key, value in identity.items() if value}},
                )
            )

        return urls


async def read_metadata(
    app: str, instance: InstanceMetadata, report: MetadataReport, consumer: URL
) -> MetadataInfo | None:
    """Return the metadata of ``app`` at the revision of ``instance``, from where ``instance`` says it is stored.

    Remote metadata is read from ``report``, and local metadata from the
    MetadataService of ``instance``, called with the parameters and the
    attributes of ``consumer``, such as those of TLS. ``None`` means the
    metadata is not stored there.

    Raises:
        ValueError: The metadata cannot be read, or the instance serves no MetadataService.
        DubboError: The report or the call failed.
        OSError: The report or the instance cannot be reached.
    """
    if instance.storage is MetadataType.REMOTE:
        return await report.get_app_metadata(app, instance.revision)
    if instance.metadata_service is None:
        raise ValueError("the instance serves no MetadataService")

    from .service.client import call_metadata_service

    service = instance.metadata_service
    url = consumer.replace(
        protocol=service.protocol,
        host=service.host,
        port=service.port,
        path=service.path,
        parameters={**consumer.parameters, **service.parameters, GROUP_KEY: app},
    )
    return await call_metadata_service(url, instance.revision)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _endpoints(text: str | None) -> dict[str, int]:
    """Read the port of each protocol in ``text``, as in ``[{"port": 50051, "protocol": "tri"}]``."""
    items = json.loads(text or "[]")
    if not isinstance(items, list):
        raise TypeError(f"endpoints must be a JSON array, not {text!r}")

    return {str(item["protocol"]): int(item["port"]) for item in items}


def _metadata_service(host: str, port: int, metadata: Mapping[str, str]) -> URL | None:
    """Return where the instance at ``host`` and ``port`` serves the MetadataService that ``metadata`` locates, if any."""
    text = metadata.get(METADATA_SERVICE_URL_PARAMS_KEY)
    if not text:
        return None

    params = json.loads(text)
    if not isinstance(params, dict):
        raise TypeError(f"the MetadataService URL parameters must be a JSON object, not {text!r}")
    protocol = str(params["protocol"])
    if protocol == "tri" and metadata.get(METADATA_SERVICE_VERSION_KEY) == METADATA_SERVICE_V2_VERSION:
        path, parameters = METADATA_SERVICE_V2, {VERSION_KEY: METADATA_SERVICE_V2_VERSION}
    else:
        path, parameters = (
            METADATA_SERVICE_V1,
            {VERSION_KEY: METADATA_SERVICE_V1_VERSION, SERIALIZATION_KEY: METADATA_SERVICE_V1_SERIALIZATION},
        )

    return URL(protocol=protocol, host=host, port=int(params.get("port", port)), path=path, parameters=parameters)
