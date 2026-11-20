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

import asyncio
import functools
import logging
from collections.abc import Collection, Mapping
from http import HTTPStatus
from typing import Any, cast

import anyio
from multidict import MultiDict

from dubbo.compression import Compressor
from dubbo.exceptions import EndOfStream, RemoteError, RpcError, Status
from dubbo.rpc.context import serving
from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Result
from dubbo.rpc.stream import Stream
from dubbo.serialization import Codec
from dubbo.transport.h2 import H2Error, H2Header, H2Headers, H2Stream

from ..attachments import attachment_headers
from ..headers import HTTP_OK, HttpHeader, TripleHeader
from ..routes import Route, RouteKey
from ..settings import TripleSettings
from .framing import frame, read_message
from .headers import CONTENT_TYPE, GrpcHeader, content_subtype, content_type, decode_timeout
from .status import status_headers, to_rpc_error, transport_error

__all__ = ["serve"]

_logger = logging.getLogger(__name__)

# The trailers of a call that ends OK without attachments, the common case.
_TRAILERS_OK = tuple(status_headers(None))
# The tri-exception-code of a response that is an exception the method threw: BIZ_EXCEPTION of RpcException.
_THROWN = b"3"


async def serve(
    stream: H2Stream,
    fields: Mapping[bytes, bytes],
    attachments: MultiDict[str | bytes],
    routes: Mapping[RouteKey, Route],
    settings: TripleSettings,
    unexported: Collection[RouteKey],
) -> None:
    """Serve the gRPC call on ``stream``, whose request headers split into ``fields`` and ``attachments``.

    A request the routes cannot serve is answered with an error status:
    UNAVAILABLE for a route in ``unexported``, which callers may retry with
    another server, and UNIMPLEMENTED for one never served. A
    grpc-timeout cancels the handler when it runs out, and the call then ends
    with DEADLINE_EXCEEDED.
    """
    try:
        route, timeout, compressor = _accept(fields, routes, settings, unexported)
    except _Rejected as rejected:
        await _reject(stream, rejected.error, rejected.http_status, rejected.headers)
        return

    response_compressor = _response_compressor(fields, settings)
    response_headers = _response_headers(
        route.subtype,
        settings.compressors.accept_encoding,
        settings.encoding if response_compressor is not None else None,
    )
    call: _UnaryCall | _GrpcServerStream
    if route.method.rpc_type is RpcType.UNARY:
        call = _UnaryCall(stream, route, settings, compressor, response_headers, response_compressor)
    else:
        call = _GrpcServerStream(stream, route, settings, compressor, response_headers, response_compressor)

    route.service.track(cast(asyncio.Task[Any], asyncio.current_task()))
    if timeout is None:
        await call.run(attachments)
        return

    with anyio.move_on_after(timeout) as scope:
        await call.run(attachments)
    if scope.cancelled_caught:
        await call.finish(RpcError(Status.DEADLINE_EXCEEDED, "the call ran out of time"), {})


async def _reject(
    stream: H2Stream, error: RpcError, http_status: HTTPStatus = HTTPStatus.OK, headers: H2Headers = ()
) -> None:
    """End a call before it reaches a service, with a response of trailers only.

    A request that is not gRPC gets an HTTP error status; a gRPC one gets
    HTTP 200 with the error in grpc-status, as gRPC clients expect.
    """
    response = (
        (HttpHeader.STATUS, b"%d" % http_status),
        (HttpHeader.CONTENT_TYPE, CONTENT_TYPE),
        *headers,
        *status_headers(error),
    )
    await stream.send_headers(response, end_stream=True)


class _Rejected(Exception):
    def __init__(self, error: RpcError, http_status: HTTPStatus = HTTPStatus.OK, headers: H2Headers = ()) -> None:
        super().__init__(error)
        self.error = error
        self.http_status = http_status
        self.headers = headers


def _accept(
    fields: Mapping[bytes, bytes],
    routes: Mapping[RouteKey, Route],
    settings: TripleSettings,
    unexported: Collection[RouteKey],
) -> tuple[Route, float | None, Compressor | None]:
    """Return the route, timeout and compressor of a request.

    Raises:
        _Rejected: The request is not one the routes can serve.
    """
    subtype = content_subtype(fields.get(HttpHeader.CONTENT_TYPE))
    if subtype is None:
        error = RpcError(
            Status.INVALID_ARGUMENT, f"invalid gRPC request content-type {fields.get(HttpHeader.CONTENT_TYPE)!r}"
        )
        raise _Rejected(error, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    timeout = None
    value = fields.get(GrpcHeader.TIMEOUT)
    if value is not None:
        try:
            timeout = decode_timeout(value)
        except ValueError as error:
            raise _Rejected(RpcError(Status.INTERNAL, str(error)), HTTPStatus.BAD_REQUEST) from None

    value = fields.get(HttpHeader.METHOD)
    if value != b"POST":
        raise _Rejected(RpcError(Status.INTERNAL, f":method {value!r} should be POST"), HTTPStatus.METHOD_NOT_ALLOWED)

    key = (
        fields.get(HttpHeader.PATH, b""),
        fields.get(TripleHeader.SERVICE_GROUP, b""),
        fields.get(TripleHeader.SERVICE_VERSION, b""),
    )
    route = routes.get(key)
    if route is None:
        path, group, version = key
        if key in unexported:
            message = f"{path!r} with group {group!r} and version {version!r} is no longer served here"
            raise _Rejected(RpcError(Status.UNAVAILABLE, message))
        message = f"no service serves {path!r} with group {group!r} and version {version!r}"
        raise _Rejected(RpcError(Status.UNIMPLEMENTED, message))

    # A content type without a subtype leaves the format to the service.
    if subtype and subtype != route.subtype:
        raise _Rejected(RpcError(Status.INTERNAL, f"no codec for content-subtype {subtype!r}"))

    try:
        compressor = settings.compressors.get(fields.get(GrpcHeader.ENCODING))
    except LookupError as error:
        accept = ((GrpcHeader.ACCEPT_ENCODING, settings.compressors.accept_encoding),)
        raise _Rejected(RpcError(Status.UNIMPLEMENTED, str(error)), headers=accept) from None

    return route, timeout, compressor


def _response_compressor(fields: Mapping[bytes, bytes], settings: TripleSettings) -> Compressor | None:
    """Return the compressor of the server when the caller accepts its encoding."""
    if settings.compressor is None:
        return None

    accepted = fields.get(GrpcHeader.ACCEPT_ENCODING, b"").split(b",")
    return settings.compressor if settings.encoding in (name.strip() for name in accepted) else None


@functools.cache
def _response_headers(subtype: bytes, accept_encoding: bytes, encoding: bytes | None) -> H2Headers:
    """Return the headers that start every response in the format ``subtype`` names."""
    headers: H2Headers = (
        (HttpHeader.STATUS, HTTP_OK),
        (HttpHeader.CONTENT_TYPE, content_type(subtype.decode())),
        (GrpcHeader.ACCEPT_ENCODING, accept_encoding),
    )
    return headers if encoding is None else (*headers, (GrpcHeader.ENCODING, encoding))


class _Call:
    """The serving side of one gRPC call."""

    def __init__(
        self,
        stream: H2Stream,
        route: Route,
        settings: TripleSettings,
        compressor: Compressor | None,
        response_headers: H2Headers,
        response_compressor: Compressor | None,
    ) -> None:
        self._stream = stream
        self._route = route
        self._max_message_size = settings.max_message_size
        self._compressor = compressor
        self._response_headers = response_headers
        self._response_compressor = response_compressor
        self._headers_sent = False

    async def finish(self, error: RpcError | None, attachments: Mapping[str, str | bytes]) -> None:
        """End the call with ``error``, or with OK when it is ``None``, sending ``attachments`` in the trailers."""
        try:
            metadata = attachment_headers(attachments) if attachments else []
        except ValueError as invalid:
            error, metadata = RpcError(Status.INTERNAL, str(invalid)), []

        trailers: tuple[H2Header, ...] = (
            _TRAILERS_OK if error is None and not metadata else (*status_headers(error), *metadata)
        )
        if self._headers_sent:
            await self._stream.send_trailers(trailers)
        else:
            # Nothing was sent: one header section carries the status and ends the call.
            self._headers_sent = True
            await self._stream.send_headers((*self._response_headers, *trailers), end_stream=True)

    async def _respond(
        self,
        codec: Codec[tuple[Any, ...]],
        value: Any,
        attachments: Mapping[str, str | bytes],
        headers: H2Headers | None = None,
    ) -> None:
        """Send ``value``, encoded with ``codec``, as the one response and end the call.

        The response starts with ``headers``, those of every response by default.
        """
        try:
            data = frame(codec.encode((value,)), self._response_compressor)
        except TypeError as error:
            await self.finish(RpcError(Status.INTERNAL, f"cannot encode the response: {error}"), attachments)
            return

        # The one response is the first thing the call sends.
        if not self._headers_sent:
            self._headers_sent = True
            await self._stream.send_headers(self._response_headers if headers is None else headers)
        await self._stream.send_data(data)
        await self.finish(None, attachments)

    async def _receive(self) -> tuple[Any, ...]:
        """Return the next request, as the values of the method's request parameters.

        Raises:
            EndOfStream: The caller has sent its last request.
            RpcError: The request is broken.
            H2Error: The stream failed.
        """
        message = await read_message(self._stream, self._max_message_size, self._compressor)
        if message is None:
            raise EndOfStream

        try:
            return self._route.messages.request.decode(message)
        except ValueError as error:
            raise RpcError(Status.INTERNAL, f"cannot decode the request: {error}") from None

    async def _receive_one(self) -> tuple[Any, ...]:
        """Return the only request of a call that takes exactly one, once the caller has ended its requests.

        Raises:
            RpcError: The request is broken, or there is none or more than one.
            H2Error: The stream failed.
        """
        try:
            arguments = await self._receive()
        except EndOfStream:
            raise RpcError(Status.UNIMPLEMENTED, "the request has no message") from None

        if await read_message(self._stream, self._max_message_size, self._compressor) is not None:
            raise RpcError(Status.UNIMPLEMENTED, "the request has more than one message")
        return arguments

    async def _invoke(self, arguments: tuple[Any, ...], attachments: MultiDict[str | bytes]) -> Result:
        method = self._route.method
        invocation = Invocation(
            interface=self._route.service.interface,
            method=method.name,
            arguments=arguments,
            attachments=attachments,
            definition=method,
        )
        with serving(attachments, peer=self._stream.peer):
            try:
                return await self._route.invoke(invocation)
            except Exception as error:
                _logger.exception(
                    "Serving %s.%s raised instead of returning a result; its caller receives INTERNAL",
                    invocation.interface,
                    invocation.method,
                )
                return Result(error=RpcError(Status.INTERNAL, f"{type(error).__name__}: {error}"))


class _UnaryCall(_Call):
    async def run(self, attachments: MultiDict[str | bytes]) -> None:
        """Receive the request, run the handler and send its response."""
        try:
            arguments = await self._receive_one()
        except RpcError as error:
            await self.finish(error, {})
            return

        result = await self._invoke(arguments, attachments)
        exception = self._route.messages.exception
        if result.error is None:
            await self._respond(self._route.messages.response, result.value, result.attachments)
        # An exception the method threw is the response where the messages carry one; a status error ends the call.
        elif exception is not None and not _is_status(result.error):
            thrown = (*self._response_headers, (TripleHeader.EXCEPTION_CODE, _THROWN))
            await self._respond(exception, result.error, result.attachments, thrown)
        else:
            await self.finish(to_rpc_error(result.error), result.attachments)


class _GrpcServerStream(_Call, Stream[Any, Any]):
    """The serving side of one streaming gRPC call, which its handler uses as its stream."""

    def __init__(
        self,
        stream: H2Stream,
        route: Route,
        settings: TripleSettings,
        compressor: Compressor | None,
        response_headers: H2Headers,
        response_compressor: Compressor | None,
    ) -> None:
        super().__init__(stream, route, settings, compressor, response_headers, response_compressor)
        self._sending = True

    async def run(self, attachments: MultiDict[str | bytes]) -> None:
        """Run the handler and end the call with how it ended."""
        # A server-streaming handler takes the request, then the response
        # stream; the others only the stream.
        if self._route.method.rpc_type is RpcType.SERVER_STREAM:
            try:
                arguments = (*await self._receive_one(), self)
            except RpcError as error:
                await self.finish(error, {})
                return
        else:
            arguments = (self,)

        result = await self._invoke(arguments, attachments)

        # A client-streaming handler returns its one response; the others
        # have sent theirs on the stream.
        if result.error is not None:
            await self.finish(to_rpc_error(result.error), result.attachments)
        elif self._route.method.rpc_type is RpcType.CLIENT_STREAM:
            await self._respond(self._route.messages.response, result.value, result.attachments)
        else:
            await self.finish(None, result.attachments)

    async def receive(self) -> Any:
        try:
            return (await self._receive())[0]
        except H2Error as error:
            raise transport_error(error) from None

    async def send(self, message: Any) -> None:
        if not self._sending:
            raise RuntimeError("the responses have ended")

        data = frame(self._route.messages.response.encode((message,)), self._response_compressor)
        try:
            if not self._headers_sent:
                self._headers_sent = True
                await self._stream.send_headers(self._response_headers)
            await self._stream.send_data(data)
        except H2Error as error:
            raise transport_error(error) from None

    async def end(self) -> None:
        # The trailers that end the responses go out when the handler returns.
        self._sending = False


def _is_status(error: Exception) -> bool:
    """Return whether ``error`` stands for a status of the call rather than an exception the method threw."""
    return isinstance(error, RpcError) and not isinstance(error, RemoteError)
