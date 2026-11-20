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

from dubbo.extension import ApplicationScope, Resource, extension_point, extensions
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invoker
from dubbo.url import URL

__all__ = ["Exporter", "Protocol", "get_protocol"]


class Exporter(Resource, typing.Protocol):
    """A service that a protocol serves."""

    @property
    def url(self) -> URL:
        """The URL being served, with the port actually bound."""
        ...

    async def aclose(self) -> None:
        """Stop accepting calls to the service, then wait for those already running."""
        ...


@extension_point("apache_dubbo.protocol")
class Protocol(Resource, typing.Protocol):
    """Expose services and call remote ones over one wire protocol.

    Implementations install under the entry point group
    ``apache_dubbo.protocol``, named by the URL scheme, such as ``tri``. One
    instance serves every address of its scheme, so URLs go to each
    `export` and `refer` rather than to the constructor, which takes no
    arguments. The servers and connections it opens are its own. `export`
    and `refer` may run concurrently, in the event loop.

    TLS comes from the parameters of each URL, or from the `ssl.SSLContext`
    its attribute `dubbo.url.SSL_CONTEXT` holds, as
    `dubbo.transport.tls.get_ssl_context` reads them.

    The application opens one instance per implementation on first use,
    through `get_protocol`; the application scope enters and exits it in a
    task of its own, and closes it as the application stops.
    """

    async def export(self, url: URL, definition: Service, invoker: Invoker) -> Exporter:
        """Serve ``invoker`` as the service ``url`` names.

        ``url`` carries the address to listen on, the service interface as its
        path and the service's settings as parameters, as in
        ``tri://0.0.0.0:50051/com.example.UserService?group=a&version=1.0``.
        The first service on an address starts the server there; later ones
        share it. A port of 0 lets the system assign one, and a missing port
        means the protocol's default.

        ``definition`` tells how to read the requests of each method, which
        the filter-wrapped ``invoker`` does not expose.

        Raises:
            TypeError: The protocol cannot carry a method of ``definition``.
            OSError: The address cannot be bound.
            ValueError: A host name with port 0 would listen on several
                ports, one per address.
        """
        ...

    async def refer(self, url: URL, definition: Service) -> Invoker:
        """Return an invoker that calls the methods of ``definition`` on the provider ``url`` names.

        ``url`` carries the provider's address, the service interface as its
        path and the service's settings as parameters, in the form `export`
        takes. Invokers for one address share a connection of the instance.
        Closing an invoker refuses new calls and waits a while for those
        running before it gives the connection back; the last one closes it.
        Neither the invoker nor the connection holds a task group or cancel
        scope of the tasks that call it, so that its owner, such as a
        directory replacing providers, may close it from any task.

        The invoker prepares how to send each method of ``definition`` when it
        is made, and finds the method of a call by `Invocation.method`. It
        returns failures of the call, including failures to reach the
        provider, in `Result.error` as `dubbo.RpcError`.

        The attachments that the invoker sets itself, such as ``token``, are
        the protocol's: a call that carries one fails with
        ``INVALID_ARGUMENT``.

        Raises:
            TypeError: The protocol cannot carry a method of ``definition``.
        """
        ...

    def announce_shutdown(self) -> None:
        """Tell the callers of the services that the application is stopping, while they keep being served.

        The application calls it once, when it starts to stop; `aclose`
        stops serving afterwards. Callers learn it as the protocol allows,
        such as from a health status or a notice on their connections, so
        that they turn to other providers. A protocol with no such means
        does nothing, as the default does.
        """

    async def aclose(self) -> None:
        """Close every server and connection the instance opened."""
        ...


async def get_protocol(name: str, scope: ApplicationScope) -> Protocol:
    """Return the protocol ``name``, the same instance for the same name in the application of ``scope``.

    The application opens it on first use and closes it when it stops.

    Raises:
        ExtensionError: No implementation has that name.
    """
    implementation = extensions.get(Protocol, name)
    return await scope.share((implementation,), implementation)
