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

from dubbo.constants import (
    DEFAULT_DUBBO_PORT,
    DEFAULT_JAVA_SERIALIZATION,
    GROUP_KEY,
    SERIALIZATION_IDS,
    SERIALIZATION_KEY,
    VERSION_KEY,
)
from dubbo.protocol.base import Protocol
from dubbo.protocol.served import ClientPool, ServedExporter, ServedService, Servers
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invoker
from dubbo.serialization import JavaSerialization, get_java_serialization
from dubbo.url import URL

from .body import service_version
from .client import DubboClient
from .connection import ConnectionSettings
from .invoker import DubboInvoker, ServiceCodecs
from .server import DubboServer

__all__ = ["DubboProtocol"]


class DubboProtocol(Protocol):
    """Serve and call services with the Dubbo protocol over TCP.

    A request names its service by interface, group and version, and its
    method by name and Java parameter descriptor. The ``serialization``
    parameter names the format, one of Java objects that has a Dubbo id,
    ``hessian2`` when absent. Without a port, the address uses port 20880.

    ``heartbeat`` and ``heartbeat.timeout``, in milliseconds, and
    ``payload``, in bytes, set the connections, as `ConnectionSettings`
    describes, with TLS as `dubbo.transport.tls.get_ssl_context` reads it,
    and ``max-concurrent-calls`` the calls a server runs at once, as
    `DubboServer` describes. The services exported on one address
    share a server, which listens until the protocol closes; each must ask
    for the same serialization and settings. Once the exporter of a service
    closes, the server answers its calls with ``SERVICE_NOT_FOUND``.
    """

    def __init__(self) -> None:
        self._servers: Servers[DubboServer] = Servers()
        self._clients: ClientPool[DubboClient] = ClientPool()
        # The codecs of each shared serialization, definition and version, which the invokers of a service share.
        self._codecs: dict[tuple[str, Service, str], ServiceCodecs] = {}

    async def export(self, url: URL, definition: Service, invoker: Invoker) -> ServedExporter:
        url = _with_defaults(url)
        serialization, serialization_id = _serialization(url)
        service = ServedService(
            interface=definition.interface,
            group=url.parameters.get(GROUP_KEY, ""),
            version=service_version(url.parameters.get(VERSION_KEY)),
            invoker=invoker,
        )

        server = await self._servers.serve(
            url,
            lambda: DubboServer(url, serialization, serialization_id),
            lambda server: server.add(service, definition),
        )
        return ServedExporter(server=server, service=service, url=url.replace(port=server.address[1]))

    async def refer(self, url: URL, definition: Service) -> Invoker:
        url = _with_defaults(url)
        serialization, serialization_id = _serialization(url)
        codecs = self._get_codecs(url, serialization, definition)
        key = (url.host, url.port, serialization_id, ConnectionSettings.from_url(url))
        client = await self._clients.acquire(key, lambda: DubboClient(url, serialization, serialization_id))

        try:
            return DubboInvoker(url, definition, client, codecs, self._clients)
        except BaseException:
            await self._clients.release(client)
            raise

    def announce_shutdown(self) -> None:
        self._servers.announce_shutdown()

    async def aclose(self) -> None:
        try:
            await self._servers.aclose()
        finally:
            await self._clients.aclose()

    def _get_codecs(self, url: URL, serialization: JavaSerialization, definition: Service) -> ServiceCodecs:
        """Return the codecs of ``definition`` at the version of ``url`` in ``serialization``, which ``url`` names.

        Those of a shared serialization are made once; the others for each call.

        Raises:
            TypeError: A method is not unary, or ``serialization`` cannot carry it.
        """
        key = (url.parameters[SERIALIZATION_KEY], definition, url.parameters.get(VERSION_KEY, ""))
        codecs = self._codecs.get(key)
        if codecs is not None:
            return codecs

        codecs = ServiceCodecs.from_definition(serialization, definition, key[2])
        if serialization.shared:
            self._codecs[key] = codecs
        return codecs


def _with_defaults(url: URL) -> URL:
    """Return ``url`` with the default port and serialization where it has none."""
    if url.port is None:
        url = url.replace(port=DEFAULT_DUBBO_PORT)
    if not url.parameters.get(SERIALIZATION_KEY):
        url = url.update_parameters({SERIALIZATION_KEY: DEFAULT_JAVA_SERIALIZATION})
    return url


def _serialization(url: URL) -> tuple[JavaSerialization, int]:
    """Return the serialization the ``serialization`` parameter of ``url`` names, with its id in the frames.

    Raises:
        ExtensionError: No serialization has that name.
        ValueError: The serialization carries no Java objects, or has no
            Dubbo id.
    """
    name = url.parameters[SERIALIZATION_KEY]
    serialization_id = SERIALIZATION_IDS.get(name)
    if serialization_id is None:
        raise ValueError(f"the serialization {name!r} has no id in the Dubbo protocol")
    return get_java_serialization(url), serialization_id
