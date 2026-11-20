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

from typing import TYPE_CHECKING, Self

from dubbo.constants import (
    DEFAULT_SHUTWAIT,
    HEALTH_ENABLED_KEY,
    REFLECTION_ENABLED_KEY,
    SERVER_KEY,
    SHUTWAIT_KEY,
)
from dubbo.extension import Resource, extensions
from dubbo.protocol.served import ServedService
from dubbo.rpc.definition import Service, get_definition
from dubbo.rpc.server import ServiceInvoker
from dubbo.serialization import Serialization
from dubbo.transport.h2 import H2Server, H2Stream
from dubbo.url import URL
from dubbo.utils.converters import boolean, milliseconds

from . import grpc
from .attachments import split_headers
from .routes import Route, RouteKey, get_routes
from .settings import TripleSettings, transport_url

if TYPE_CHECKING:
    from .builtin import HealthService

__all__ = ["TripleServer"]


class TripleServer(Resource):
    """Serves the services exported on one address, routing each stream by path, group and version.

    Entering it starts listening; closing it stops.
    ``max-receive-message-size`` is the bytes of the largest request, 4 MiB
    when absent. ``compressor`` names the compression of the responses, used
    for the callers whose grpc-accept-encoding lists it; responses are sent as
    they are otherwise.

    ``health-enabled=true`` adds the gRPC health service, which reports each
    exported service as serving under its interface and its service key.
    ``reflection-enabled=true`` adds the gRPC reflection service, v1 and
    v1alpha, which describes the services whose protobuf files are loaded.
    Neither is registered with a registry.

    Raises:
        ValueError: A parameter is invalid.
    """

    def __init__(self, url: URL) -> None:
        url = transport_url(url)
        self.routes: dict[RouteKey, Route] = {}
        # Routes of the services removed since, whose callers are told to try another server.
        self._unexported: set[RouteKey] = set()
        # Seconds an unexported service waits for its running calls before they are cancelled.
        self.shutwait = url.get_parameter(SHUTWAIT_KEY, milliseconds, DEFAULT_SHUTWAIT)
        self._parameters = url.parameters
        self._settings = TripleSettings.from_url(url)
        self._server = extensions.get(H2Server, url.parameters.get(SERVER_KEY))(url, self._handle)

        self._builtins: set[ServedService] = set()
        self._health: HealthService | None = None
        if url.get_parameter(HEALTH_ENABLED_KEY, boolean, False):
            from . import builtin

            self._health = builtin.HealthService()
            self._add_builtin(url, self._health)
        if url.get_parameter(REFLECTION_ENABLED_KEY, boolean, False):
            from . import builtin

            self._add_builtin(url, builtin.ReflectionService(self._interfaces))
            self._add_builtin(url, builtin.ReflectionV1AlphaService(self._interfaces))

    @property
    def address(self) -> tuple[str, int]:
        return self._server.address

    def add(self, service: ServedService, definition: Service, serialization: Serialization) -> None:
        """Start routing the methods of ``definition`` to ``service``.

        Raises:
            TypeError: ``serialization`` cannot carry a method.
            ValueError: Another service already serves one of the paths with
                the same group and version.
        """
        routes = get_routes(service, definition, serialization)
        taken = routes.keys() & self.routes.keys()
        if taken:
            path, group, version = next(iter(taken))
            raise ValueError(f"{path.decode()} is already exported with group {group!r} and version {version!r}")

        self.routes |= routes
        self._unexported -= routes.keys()
        self._report_health()

    def remove(self, service: ServedService) -> None:
        """Stop routing to ``service``; its calls then fail with UNAVAILABLE, so that callers retry elsewhere."""
        self._unexported |= {key for key, route in self.routes.items() if route.service is service}
        self.routes = {key: route for key, route in self.routes.items() if route.service is not service}
        self._report_health()

    def check(self, url: URL) -> None:
        """Check that ``url`` asks for the settings this server was created with.

        Raises:
            ValueError: A setting of the server differs, such as a message
                limit, the TLS files or an HTTP/2 parameter.
        """
        parameters = transport_url(url).parameters
        differing = sorted(
            key
            for key in parameters.keys() | self._parameters.keys()
            if parameters.get(key) != self._parameters.get(key)
        )
        if differing:
            host, port = self.address
            raise ValueError(f"the server at {host}:{port} runs with other {', '.join(differing)}")

    def announce_shutdown(self) -> None:
        """Report every service as not serving and send the connections a GOAWAY, while serving on."""
        if self._health is not None:
            self._health.announce_shutdown()
        self._server.announce_shutdown()

    async def aclose(self) -> None:
        # Watches of the health service would otherwise hold the server open.
        if self._health is not None:
            self._health.close()
        await self._server.aclose()

    async def __aenter__(self) -> Self:
        await self._server.__aenter__()
        return self

    def _add_builtin(self, url: URL, implementation: object) -> None:
        from dubbo.serialization.protobuf import ProtobufSerialization

        definition = get_definition(implementation)
        service = ServedService(
            interface=definition.interface,
            group="",
            version="",
            invoker=ServiceInvoker.from_implementation(implementation, url),
        )
        self._builtins.add(service)
        self.add(service, definition, ProtobufSerialization(url))

    def _interfaces(self) -> set[str]:
        return {route.service.interface for route in self.routes.values()}

    def _report_health(self) -> None:
        if self._health is None:
            return

        services = {route.service for route in self.routes.values()} - self._builtins
        self._health.update({key for service in services for key in (service.interface, service.key)})

    async def _handle(self, stream: H2Stream) -> None:
        fields, attachments = split_headers(await stream.receive_headers())
        await grpc.serve(stream, fields, attachments, self.routes, self._settings, self._unexported)
