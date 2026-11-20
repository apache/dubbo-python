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

from collections.abc import Mapping
from typing import Self

import attrs

from dubbo.constants import (
    DEFAULT_SHUTWAIT,
    DUBBO_VERSION_KEY,
    GENERIC_KEY,
    GROUP_KEY,
    INTERFACE_KEY,
    PATH_KEY,
    SHUTWAIT_KEY,
    TIMEOUT_KEY,
    TOKEN_KEY,
    VERSION_KEY,
)
from dubbo.exceptions import RpcError, Status
from dubbo.protocol.generic import GENERIC_INVOKE, invoke_arguments
from dubbo.protocol.java import caller_error
from dubbo.protocol.served import Calls, ClientPool, call_within, method_timeout
from dubbo.rpc.definition import RpcType, Service
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.serialization import JavaSerialization
from dubbo.url import URL
from dubbo.utils.converters import milliseconds, to_milliseconds

from .body import MethodCodec, ResponseCodec, ResponseStatus, status_error, to_attachments
from .client import DubboClient

__all__ = ["DubboInvoker", "ServiceCodecs"]

# The attachments that route a request and bound it, which only the URL and the timeout of the invoker set.
_RESERVED = frozenset({PATH_KEY, INTERFACE_KEY, GROUP_KEY, VERSION_KEY, TOKEN_KEY, TIMEOUT_KEY, DUBBO_VERSION_KEY})


@attrs.define(frozen=True, kw_only=True)
class ServiceCodecs:
    """How the calls of the methods of one service and version travel in one serialization.

    Codecs keep no state between messages, so the invokers of a service share them.
    """

    responses: ResponseCodec
    methods: Mapping[str, MethodCodec]
    generic: MethodCodec

    @classmethod
    def from_definition(cls, serialization: JavaSerialization, definition: Service, version: str) -> Self:
        """Raises:
        TypeError: A method is not unary, or ``serialization`` cannot carry it.
        """
        responses = ResponseCodec(serialization)
        methods = {}
        for method in definition.methods:
            if method.rpc_type is not RpcType.UNARY:
                raise TypeError(f"Dubbo carries unary calls, but {method.name} is {method.rpc_type.value}")
            methods[method.name] = MethodCodec(responses, definition.interface, version, method)
        generic = MethodCodec(responses, definition.interface, version, GENERIC_INVOKE)
        return cls(responses=responses, methods=methods, generic=generic)


class DubboInvoker(Invoker):
    """Calls the methods of one remote service with a share in a client of ``clients``.

    Each method is prepared when the invoker is made, so a call only encodes,
    sends and decodes. A call runs for at most the milliseconds of
    ``{method}.timeout``, else of ``timeout``, one second when absent, and then ends with
    ``DEADLINE_EXCEEDED``; the provider learns the timeout from the
    ``timeout`` attachment. Each call attaches the ``token`` of ``url``; a
    call whose own attachments set one of those that route or bound it, such
    as ``group`` or ``timeout``, fails with ``INVALID_ARGUMENT``. An
    exception the provider raises reaches the caller as a `RemoteError`.
    Closing the invoker refuses new calls, waits for those running as long as
    ``shutwait``, ten seconds when absent, then gives the share back.
    """

    def __init__(
        self,
        url: URL,
        definition: Service,
        client: DubboClient,
        codecs: ServiceCodecs,
        clients: ClientPool[DubboClient],
    ) -> None:
        """``codecs`` are those of ``definition`` at the version of ``url``."""
        self._url = url
        self._responses = codecs.responses
        self._methods = methods = codecs.methods
        self._generic = codecs.generic

        attachments = {PATH_KEY: definition.interface, INTERFACE_KEY: definition.interface}
        for key in (GROUP_KEY, VERSION_KEY, TOKEN_KEY):
            if url.parameters.get(key):
                attachments[key] = url.parameters[key]
        self._attachments = attachments
        self._timeouts = {name: method_timeout(url, name) for name in methods}
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
            method = self._generic
            arguments = invoke_arguments(self._responses.serialization, invocation.definition, invocation.arguments)
            timeout = method_timeout(self._url, invocation.method)
        else:
            known = self._methods.get(invocation.method)
            if known is None:
                return Result(error=RpcError(Status.UNIMPLEMENTED, f"the service has no method {invocation.method!r}"))
            method, arguments, timeout = known, invocation.arguments, self._timeouts[invocation.method]
        if self._closed:
            return Result(error=RpcError(Status.UNAVAILABLE, "the invoker is closed"))

        reserved = _RESERVED.intersection(invocation.attachments)
        if reserved:
            message = f"the attachments {', '.join(sorted(reserved))} are the protocol's to set"
            return Result(error=RpcError(Status.INVALID_ARGUMENT, message))

        attachments = {**invocation.attachments, **self._attachments, TIMEOUT_KEY: to_milliseconds(timeout)}
        if invocation.generic is not None:
            attachments[GENERIC_KEY] = invocation.generic
        try:
            body = method.encode_request(arguments, attachments)
        except (TypeError, ValueError) as error:
            return Result(error=RpcError(Status.INVALID_ARGUMENT, f"cannot encode the request: {error}"))

        self._calls.enter()
        try:
            return await call_within(timeout, invocation.method, self._call(method, body))
        finally:
            self._calls.leave()

    async def aclose(self) -> None:
        if self._closed:
            return

        self._closed = True
        try:
            await self._calls.drain(self._shutwait)
        finally:
            await self._clients.release(self._client)

    async def _call(self, method: MethodCodec, body: bytes) -> Result:
        try:
            status, data = await self._client.call(body)
        except RpcError as error:
            return Result(error=error)

        try:
            if status != ResponseStatus.OK:
                return Result(error=status_error(status, self._responses.decode_message(data)))
            response = method.decode_response(data)
        except ValueError as error:
            return Result(error=RpcError(Status.INTERNAL, f"cannot decode the response: {error}"))

        attachments = to_attachments(response.attachments)
        if response.exception is not None:
            return Result(error=caller_error(response.exception), attachments=attachments)
        return Result(value=response.value, attachments=attachments)
