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
import contextlib
import math
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any

import anyio
from multidict import MultiDict

from dubbo.compression import Compressor
from dubbo.exceptions import EndOfStream, RpcError, Status
from dubbo.rpc.definition import Method, RpcType
from dubbo.rpc.invocation import Invocation, Result
from dubbo.rpc.stream import BidiStream, ClientStream, ServerStream
from dubbo.serialization import Codec
from dubbo.transport.h2 import H2Client, H2Error, H2Headers, H2Stream, H2StreamResetError

from ..attachments import attachment_headers, split_headers
from ..headers import HttpHeader, TripleHeader
from ..messages import MethodMessages
from ..settings import TripleSettings
from .framing import frame, read_message
from .headers import GrpcHeader, content_subtype, encode_timeout
from .status import response_error, to_rpc_error, trailer_error, transport_error

__all__ = ["GrpcMethod"]


# How much sooner than the caller a provider may reach the deadline of a call: a timer of asyncio fires up to the
# resolution of its clock early, and before Python 3.13 the clock of Windows moves in steps of 16 ms on both sides.
_DEADLINE_SKEW = 0.1


class GrpcMethod:
    """Calls one method of a service, with everything that does not change between calls made once.

    Args:
        method: The method called.
        headers: The request headers every call of the method starts with:
            the pseudo-header fields, ``:path`` among them, then the others.
        messages: How the values of the method travel.
        settings: Message limits and compression of the invoker.
    """

    def __init__(
        self,
        method: Method,
        headers: H2Headers,
        messages: MethodMessages,
        settings: TripleSettings,
    ) -> None:
        self.rpc_type = method.rpc_type
        self._headers = headers
        self._pseudo_count = sum(1 for name, _ in headers if name.startswith(b":"))
        self._request = messages.request
        self._response = messages.response
        self._exception = messages.exception
        self._settings = settings

    async def call(self, client: H2Client, invocation: Invocation, timeout: float) -> Result:
        """Make a unary call and return how it ended.

        ``timeout`` is the seconds the call may take, which the request declares as its grpc-timeout.
        A call that its provider ends as ``DEADLINE_EXCEEDED`` when its own
        deadline is at most ``_DEADLINE_SKEW`` away waits for that deadline
        instead, so that the caller's deadline ends it, as an AnyIO deadline
        or the ``timeout``, whichever side reached it first; a caller that
        shields itself from cancellation gets the error ``_DEADLINE_SKEW``
        after its deadline.
        """
        # The clock of AnyIO on asyncio, read directly: asking AnyIO for the time and the deadline in each
        # call took 0.5 µs of the 16 a call costs its caller, measured at 128 at once on uvloop.
        now = asyncio.get_running_loop().time()
        # The time left first, so that the grpc-timeout is never above timeout by a rounding of the clock.
        remaining = min(anyio.current_effective_deadline() - now, timeout)
        deadline = now + remaining
        try:
            headers = self._request_headers(invocation.attachments, remaining)
            data = frame(self._request.encode(invocation.arguments), self._settings.compressor)
        except (TypeError, ValueError) as error:
            return Result(error=RpcError(Status.INTERNAL, str(error)))
        except RpcError as error:
            return Result(error=error)

        attachments: MultiDict[str | bytes] = MultiDict()
        try:
            stream = await client.open_stream(headers)
            async with stream:
                await _send(stream, data, end_stream=True)
                try:
                    compressor, thrown = await _receive_headers(stream, self._settings, attachments)
                except _TrailersOnly:
                    raise RpcError(Status.UNIMPLEMENTED, "the response has no message") from None

                max_size = self._settings.max_message_size
                message = await read_message(stream, max_size, compressor)
                if message is None:
                    await _receive_trailers(stream, attachments)
                    raise RpcError(Status.UNIMPLEMENTED, "the response has no message")
                if await read_message(stream, max_size, compressor) is not None:
                    raise RpcError(Status.UNIMPLEMENTED, "the response has more than one message")
                await _receive_trailers(stream, attachments)
        except RpcError as error:
            if error.status is Status.DEADLINE_EXCEEDED and deadline - anyio.current_time() <= _DEADLINE_SKEW:
                # Past the deadline, so that the caller's own deadline wakes the call, and not a timer beside it.
                await anyio.sleep_until(deadline + _DEADLINE_SKEW)
            return Result(error=error, attachments=attachments)
        except H2Error as error:
            return Result(error=transport_error(error), attachments=attachments)

        # Only wrapped messages carry a thrown exception as the response; elsewhere it travels as the status.
        codec = self._exception if thrown and self._exception is not None else self._response
        try:
            value = codec.decode(message)[0]
        except ValueError as error:
            return Result(
                error=RpcError(Status.INTERNAL, f"cannot decode the response: {error}"), attachments=attachments
            )
        if codec is self._exception:
            return Result(error=value, attachments=attachments)
        return Result(value=value, attachments=attachments)

    async def open(self, client: H2Client, invocation: Invocation, *, on_exit: Callable[[], None]) -> Result:
        """Open a streaming call and return it as the result's value, or the error that kept it from opening.

        ``on_exit`` is called once the opened call exits.
        """
        try:
            headers = self._request_headers(
                invocation.attachments, anyio.current_effective_deadline() - anyio.current_time()
            )
            # A server-streaming call sends its one request when the first response is awaited.
            request = None
            if self.rpc_type is RpcType.SERVER_STREAM:
                request = frame(self._request.encode(invocation.arguments), self._settings.compressor)
        except (TypeError, ValueError) as error:
            return Result(error=RpcError(Status.INTERNAL, str(error)))
        except RpcError as error:
            return Result(error=error)

        try:
            stream = await client.open_stream(headers)
        except H2Error as error:
            return Result(error=transport_error(error))

        single = self.rpc_type is RpcType.CLIENT_STREAM
        call = GrpcClientStream(stream, self._request, self._response, self._settings, request, on_exit, single=single)
        return Result(value=call)

    def _request_headers(self, attachments: Mapping[str, str | bytes], remaining: float) -> H2Headers:
        """Return the headers of a call that has ``remaining`` seconds before its deadline, as its grpc-timeout.

        Raises:
            RpcError: The deadline has passed.
            ValueError: An attachment cannot travel as a header.
        """
        budget: H2Headers = ()
        if not math.isinf(remaining):
            if remaining <= 0:
                raise RpcError(Status.DEADLINE_EXCEEDED, "the call ran out of time before it started")
            budget = ((GrpcHeader.TIMEOUT, encode_timeout(remaining)),)

        if not budget and not attachments:
            return self._headers

        # grpc-timeout follows the pseudo-header fields.
        split = self._pseudo_count
        return (
            *self._headers[:split],
            *budget,
            *self._headers[split:],
            *(attachment_headers(attachments) if attachments else ()),
        )


class GrpcClientStream(BidiStream[Any, Any], ClientStream[Any, Any], ServerStream[Any]):
    """The caller's side of one streaming call; leaving ``async with`` cancels the call if it still runs.

    Args:
        request: The framed request of a server-streaming call, which has
            only that one.
        on_exit: Called once the stream exits.
        single: Whether the call has exactly one response, as a
            client-streaming call does.
    """

    def __init__(
        self,
        stream: H2Stream,
        request_codec: Codec[tuple[Any, ...]],
        response_codec: Codec[tuple[Any, ...]],
        settings: TripleSettings,
        request: bytes | None,
        on_exit: Callable[[], None],
        *,
        single: bool = False,
    ) -> None:
        self._stream = stream
        self._single = single
        self._request_codec = request_codec
        self._response_codec = response_codec
        self._settings = settings
        # The one request goes out when the first response is awaited: inside
        # the caller's ``async with``, which closes the stream if sending fails.
        self._unsent_request = request
        self._on_exit: Callable[[], None] | None = on_exit
        self._response_attachments: MultiDict[str | bytes] = MultiDict()
        self._compressor: Compressor | None = None
        self._headers_received = False
        self._ended = False
        self._error: RpcError | None = None

    @property
    def response_attachments(self) -> MultiDict[str | bytes]:
        # Filled in as the response headers and trailers arrive.
        return self._response_attachments

    async def send(self, message: Any) -> None:
        # A call that failed fails each send as it ended.
        if self._error is not None:
            raise to_rpc_error(self._error)

        data = frame(self._request_codec.encode((message,)), self._settings.compressor)
        try:
            await _send(self._stream, data)
        except H2Error as error:
            raise transport_error(error) from None

    async def end(self) -> None:
        try:
            await self._stream.end()
        except H2StreamResetError:
            # The server has ended the call; receive reports how.
            pass
        except H2Error as error:
            raise transport_error(error) from None

    async def receive(self) -> Any:
        # A finished call keeps answering as it ended.
        if self._error is not None:
            raise to_rpc_error(self._error)
        if self._ended:
            raise EndOfStream

        try:
            message = await self._next_message()
        except RpcError as error:
            self._error = error
            raise

        if message is None:
            self._ended = True
            raise EndOfStream

        try:
            return self._response_codec.decode(message)[0]
        except ValueError as error:
            raise RpcError(Status.INTERNAL, f"cannot decode the response: {error}") from None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self._stream.__aexit__(exc_type, exc, traceback)
        finally:
            on_exit, self._on_exit = self._on_exit, None
            if on_exit is not None:
                on_exit()

    async def _next_message(self) -> bytes | None:
        """Return the next response message, or ``None`` once the call has ended OK.

        Raises:
            RpcError: The call failed.
        """
        try:
            if self._unsent_request is not None:
                request, self._unsent_request = self._unsent_request, None
                await _send(self._stream, request, end_stream=True)

            if not self._headers_received:
                self._headers_received = True
                self._compressor, _ = await _receive_headers(self._stream, self._settings, self._response_attachments)

            max_size = self._settings.max_message_size
            message = await read_message(self._stream, max_size, self._compressor)
            if message is None:
                await _receive_trailers(self._stream, self._response_attachments)
            elif self._single:
                if await read_message(self._stream, max_size, self._compressor) is not None:
                    raise RpcError(Status.UNIMPLEMENTED, "the response has more than one message")
                await _receive_trailers(self._stream, self._response_attachments)
                self._ended = True
        except H2Error as error:
            raise transport_error(error) from None
        except _TrailersOnly:
            message = None

        if message is None and self._single:
            raise RpcError(Status.UNIMPLEMENTED, "the response has no message")
        return message


class _TrailersOnly(Exception):
    """The response headers ended the call with OK, so no message follows."""


async def _send(stream: H2Stream, data: bytes, *, end_stream: bool = False) -> None:
    # A reset means the server has ended the call; the response reports how.
    with contextlib.suppress(H2StreamResetError):
        await stream.send_data(data, end_stream=end_stream)


async def _receive_headers(
    stream: H2Stream, settings: TripleSettings, attachments: MultiDict[str | bytes]
) -> tuple[Compressor | None, bool]:
    """Receive the response headers, adding their attachments; return the compressor they name and whether the message is a thrown exception.

    Raises:
        RpcError: The response is not a gRPC one, or is trailers only,
            reporting an error.
        _TrailersOnly: The response is trailers only, reporting OK.
    """
    fields, received = split_headers(await stream.receive_headers())
    attachments.extend(received)

    # The grpc-status of a gRPC response decides the call; the HTTP status counts only when there is none.
    if GrpcHeader.STATUS in fields and content_subtype(fields.get(HttpHeader.CONTENT_TYPE)) is not None:
        error = trailer_error(fields)
        if error is not None:
            raise error
        raise _TrailersOnly

    error = response_error(fields)
    if error is not None:
        raise error

    thrown = fields.get(TripleHeader.EXCEPTION_CODE, b"0") != b"0"
    try:
        return settings.compressors.get(fields.get(GrpcHeader.ENCODING)), thrown
    except LookupError as error:
        raise RpcError(Status.INTERNAL, str(error)) from None


async def _receive_trailers(stream: H2Stream, attachments: MultiDict[str | bytes]) -> None:
    """Receive the trailers, adding their attachments.

    Raises:
        RpcError: The trailers report an error.
    """
    fields, received = split_headers(await stream.receive_trailers() or ())
    attachments.extend(received)

    error = trailer_error(fields)
    if error is not None:
        raise error
