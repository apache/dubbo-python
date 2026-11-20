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

import importlib.metadata
import platform
from collections.abc import Mapping

import attrs
from multidict import MultiDict

from dubbo.constants import (
    APPLICATION_KEY,
    DEFAULT_JAVA_SERIALIZATION,
    DEFAULT_SHUTWAIT,
    GENERIC_KEY,
    GROUP_KEY,
    SERIALIZATION_KEY,
    SHUTWAIT_KEY,
    SSL_ENABLED_KEY,
    TOKEN_KEY,
    VERSION_KEY,
)
from dubbo.exceptions import RpcError, Status
from dubbo.extension import ExtensionError
from dubbo.protocol.generic import GENERIC_INVOKE, invoke_arguments
from dubbo.protocol.served import Calls, ClientPool, call_within, method_timeout
from dubbo.rpc.definition import Method, RpcType, Service
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.serialization import JavaSerialization, Serialization, get_java_serialization
from dubbo.transport.h2 import H2Client, H2Headers
from dubbo.url import URL
from dubbo.utils.converters import boolean, milliseconds

from .grpc import GrpcMethod
from .grpc.headers import GrpcHeader, content_type
from .headers import HttpHeader, TripleHeader
from .messages import MethodMessages, method_messages
from .settings import TripleSettings, transport_url

__all__ = ["TripleInvoker"]

# The headers that carry URL parameters, by parameter key.
_PARAMETER_HEADERS = (
    (TripleHeader.SERVICE_GROUP, GROUP_KEY),
    (TripleHeader.SERVICE_VERSION, VERSION_KEY),
    (TripleHeader.CONSUMER_APPLICATION, APPLICATION_KEY),
)
# The library, its version and the platform, in the form gRPC recommends.
_USER_AGENT = (
    f"grpc-python-dubbo/{importlib.metadata.version('apache-dubbo')} "
    f"({platform.system()}; {platform.python_implementation()}/{platform.python_version()})"
).encode()


class TripleInvoker(Invoker):
    """Calls the methods of one remote service over a share in an HTTP/2 client of ``clients``.

    Each method's call is prepared when the invoker is made, so a call only
    encodes, sends and receives. Closing the invoker refuses new calls, waits
    for those running as long as ``shutwait``, ten seconds when absent, then
    gives the share back. It is available while open and while the client is.
    A streaming call runs until its stream exits. A unary call runs until its
    result, for at most the milliseconds of ``{method}.timeout``, else of
    ``timeout``, and then ends with ``DEADLINE_EXCEEDED``.

    Each call attaches the ``token`` of ``url``, which the provider
    registers; one that carries a ``token`` itself fails with
    ``INVALID_ARGUMENT``.

    A generic call travels as ``$invoke`` of the service, its values wrapped
    in the format of ``serialization`` when that carries Java objects, else
    in ``hessian2``.

    ``compressor`` names the compression of the requests, such as ``gzip``;
    they are sent as they are when it is absent. ``max-receive-message-size``
    is the bytes of the largest response, 4 MiB when absent.

    Raises:
        ValueError: A parameter is invalid, or names no installed compressor.
    """

    def __init__(
        self,
        url: URL,
        definition: Service,
        client: H2Client,
        serialization: Serialization,
        messages: Mapping[str, MethodMessages],
        clients: ClientPool[H2Client],
    ) -> None:
        """``messages`` tells how the values of each method of ``definition`` travel in ``serialization``."""
        self._url = url
        self._interface = definition.interface
        self._serialization = serialization
        self._settings = settings = TripleSettings.from_url(transport_url(url))
        scheme = b"https" if url.get_parameter(SSL_ENABLED_KEY, boolean, False) else b"http"
        # Pseudo-header fields precede the others; :path follows them in each method's headers.
        self._pseudo: H2Headers = (
            (HttpHeader.METHOD, b"POST"),
            (HttpHeader.SCHEME, scheme),
            (HttpHeader.AUTHORITY, f"{url.host}:{url.port}".encode()),
        )
        # The fields after :path and content-type.
        self._fields: H2Headers = (
            (HttpHeader.TE, b"trailers"),
            (HttpHeader.USER_AGENT, _USER_AGENT),
            (GrpcHeader.ACCEPT_ENCODING, settings.compressors.accept_encoding),
            *(((GrpcHeader.ENCODING, settings.encoding),) if settings.compressor is not None else ()),
            *((name, url.parameters[key].encode()) for name, key in _PARAMETER_HEADERS if url.parameters.get(key)),
        )

        self._methods = {method.name: self._grpc_method(method, messages[method.name]) for method in definition.methods}
        self._generic: tuple[GrpcMethod, JavaSerialization] | None = None
        self._timeouts = {
            method.name: method_timeout(url, method.name)
            for method in definition.methods
            if method.rpc_type is RpcType.UNARY
        }
        self._token = url.parameters.get(TOKEN_KEY)
        self._shutwait = url.get_parameter(SHUTWAIT_KEY, milliseconds, DEFAULT_SHUTWAIT)
        self._client = client
        self._clients = clients
        self._closed = False
        self._calls = Calls()

    @property
    def url(self) -> URL:
        return self._url

    @property
    def available(self) -> bool:
        return not self._closed and self._client.available

    async def invoke(self, invocation: Invocation) -> Result:
        if invocation.generic is not None:
            try:
                method, serialization = self._generic_method()
                arguments = invoke_arguments(serialization, invocation.definition, invocation.arguments)
            except (ExtensionError, TypeError, ValueError) as error:
                # The cause of a plugin that cannot load tells what to install.
                reason = f"{error}: {error.__cause__}" if error.__cause__ is not None else str(error)
                message = f"cannot call {invocation.method} generically: {reason}"
                return Result(error=RpcError(Status.UNIMPLEMENTED, message))
            timeout = method_timeout(self._url, invocation.method)
        else:
            known = self._methods.get(invocation.method)
            if known is None:
                return Result(error=RpcError(Status.UNIMPLEMENTED, f"the service has no method {invocation.method!r}"))
            method, arguments, timeout = known, invocation.arguments, self._timeouts.get(invocation.method)
        if self._closed:
            return Result(error=RpcError(Status.UNAVAILABLE, "the invoker is closed"))
        if TOKEN_KEY in invocation.attachments:
            return Result(error=RpcError(Status.INVALID_ARGUMENT, "the attachment token is the protocol's to set"))

        if self._token or invocation.generic is not None:
            # A copy: each attempt on another provider sends its own attachments.
            attachments = MultiDict(invocation.attachments)
            if self._token:
                attachments[TOKEN_KEY] = self._token
            if invocation.generic is not None:
                attachments[GENERIC_KEY] = invocation.generic
            invocation = attrs.evolve(invocation, arguments=arguments, attachments=attachments)

        self._calls.enter()
        # A unary call has a timeout; a streaming one runs until its stream exits.
        if timeout is not None:
            try:
                return await call_within(timeout, invocation.method, method.call(self._client, invocation, timeout))
            finally:
                self._calls.leave()

        try:
            result = await method.open(self._client, invocation, on_exit=self._calls.leave)
        except BaseException:
            self._calls.leave()
            raise

        if result.error is not None:
            self._calls.leave()
        return result

    async def aclose(self) -> None:
        if self._closed:
            return

        self._closed = True
        try:
            await self._calls.drain(self._shutwait)
        finally:
            await self._clients.release(self._client)

    def _grpc_method(self, method: Method, messages: MethodMessages) -> GrpcMethod:
        """Return the call of ``method`` of the service, its values travelling as ``messages``."""
        headers = (
            *self._pseudo,
            (HttpHeader.PATH, f"/{self._interface}/{method.name}".encode()),
            (HttpHeader.CONTENT_TYPE, content_type(messages.content_subtype)),
            *self._fields,
        )
        return GrpcMethod(method, headers, messages, self._settings)

    def _generic_method(self) -> tuple[GrpcMethod, JavaSerialization]:
        """Return the call of ``$invoke`` and the format of Java objects of its values, made on the first generic call.

        Raises:
            ExtensionError: The format of Java objects it needs cannot be loaded.
            ValueError: That format carries no Java objects.
        """
        if self._generic is None:
            java = self._serialization
            if not isinstance(java, JavaSerialization):
                java = get_java_serialization(
                    self._url.update_parameters({SERIALIZATION_KEY: DEFAULT_JAVA_SERIALIZATION})
                )
            self._generic = self._grpc_method(GENERIC_INVOKE, method_messages(java, GENERIC_INVOKE)), java

        return self._generic
