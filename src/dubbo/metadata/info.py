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

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Self

import attrs

from dubbo.url import service_key
from dubbo.utils import freeze_mapping

__all__ = ["EMPTY_REVISION", "MetadataInfo", "ServiceInfo"]

# The revision of an application that serves no service.
EMPTY_REVISION = "0"


@attrs.define(frozen=True, kw_only=True)
class ServiceInfo:
    """One service an application serves, as its metadata describes it to consumers.

    Attributes:
        name: Interface name of the service.
        group: Service group, if any.
        version: Service version, if any.
        protocol: Protocol the service is served with, such as ``tri``.
        port: Port the service is served on; 0 or less means the port of the
            instance, or of its endpoint for the protocol.
        path: Path the service is called by, usually its interface name.
        params: Parameters of the service URL, such as ``methods``.
    """

    name: str
    group: str | None = None
    version: str | None = None
    protocol: str
    port: int
    path: str
    params: Mapping[str, str] = attrs.field(factory=dict, converter=freeze_mapping, hash=False)

    @property
    def service_key(self) -> str:
        """``group/name:version``, leaving out the parts that are not set."""
        return service_key(self.name, self.group, self.version)

    @property
    def match_key(self) -> str:
        """The service key and the protocol, as in ``group/name:version:tri``; metadata is keyed by it."""
        return f"{self.service_key}:{self.protocol}"

    def describe(self) -> str:
        """Return the text that the revision hashes for this service."""
        # The parameters render as sorted key=value entries separated by a comma and a space.
        params = ", ".join(f"{key}={value}" for key, value in sorted(self.params.items()))
        return f"{self.match_key}{self.port}{self.path}{{{params}}}"


@attrs.define(frozen=True, kw_only=True)
class MetadataInfo:
    """The services of an application, which its instances register by revision.

    Attributes:
        app: Application name.
        services: The services, keyed by their match key.
    """

    app: str
    services: Mapping[str, ServiceInfo] = attrs.field(factory=dict, converter=freeze_mapping, hash=False)

    @classmethod
    def from_services(cls, app: str, services: list[ServiceInfo]) -> Self:
        """Return the metadata of ``app`` serving ``services``."""
        return cls(app=app, services={service.match_key: service for service in services})

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Read the JSON a registry stores for ``remote`` metadata.

        Raises:
            ValueError: The text is not such JSON.
        """
        try:
            data = json.loads(text)
            services = [_parse_service(item) for item in data.get("services", {}).values()]
            return cls.from_services(str(data["app"]), services)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid metadata JSON: {error}") from None

    @property
    def revision(self) -> str:
        """The MD5 of the application and its services in hexadecimal, or ``0`` without services.

        Instances that serve the same services share one revision. Consumers
        only compare revisions.
        """
        if not self.services:
            return EMPTY_REVISION

        text = self.app + "".join(self.services[key].describe() for key in sorted(self.services))
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    def to_json(self) -> str:
        """Return the JSON a registry stores for ``remote`` metadata."""
        services = {key: _service_json(service) for key, service in self.services.items()}
        return json.dumps(
            {"app": self.app, "revision": self.revision, "services": services},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _service_json(service: ServiceInfo) -> dict[str, Any]:
    fields = {
        "name": service.name,
        "group": service.group,
        "version": service.version,
        "protocol": service.protocol,
        "port": service.port,
        "path": service.path,
        "params": dict(service.params),
    }
    return {key: value for key, value in fields.items() if value is not None}


def _parse_service(data: Mapping[str, Any]) -> ServiceInfo:
    params = data.get("params") or {}
    return ServiceInfo(
        name=str(data["name"]),
        group=_optional(data.get("group")),
        version=_optional(data.get("version")),
        protocol=str(data["protocol"]),
        port=int(data.get("port", -1)),
        path=str(data.get("path") or data["name"]),
        params={str(key): str(value) for key, value in params.items()},
    )


def _optional(value: object) -> str | None:
    # Absent, null and empty fields all mean "not set".
    return str(value) if value else None
