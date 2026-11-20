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
import logging
import math
from typing import Any, Self

import anyio
import attrs

from dubbo.constants import (
    DEFAULT_MAX_CONCURRENT_CALLS,
    DEFAULT_SHUTWAIT,
    DUBBO_VERSION,
    DUBBO_VERSION_KEY,
    GROUP_KEY,
    MAX_CONCURRENT_CALLS_KEY,
    SERIALIZATION_IDS,
    SERIALIZATION_KEY,
    SHUTWAIT_KEY,
    TIMEOUT_KEY,
)
from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.extension import Resource
from dubbo.protocol.generic import builtin_methods
from dubbo.protocol.java import java_exception
from dubbo.protocol.served import ServedService
from dubbo.rpc.context import serving
from dubbo.rpc.definition import Method, RpcType, Service
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.serialization import JavaSerialization
from dubbo.transport.listener import abort_handshakes, create_listener
from dubbo.transport.tls import get_ssl_context, ssl_handshake_timeout
from dubbo.url import URL
from dubbo.utils import release_shield, wait_then_cancel
from dubbo.utils.converters import milliseconds

from .body import (
    MethodCodec,
    RequestHead,
    ResponseCodec,
    ResponseStatus,
    read_request_head,
    supports_response_attachments,
    to_attachments,
)
from .connection import FLAG_REQUEST, FLAG_TWO_WAY, SERIALIZATION_MASK, ConnectionSettings, DubboConnection, EventBodies

__all__ = ["DubboServer"]

_logger = logging.getLogger(__name__)

# A service is found by its interface, group and version.
_ServiceKey = tuple[str, str, str]
# A method is found by its interface, the version of its service, its name and its descriptor, whatever the group.
_MethodKey = tuple[str, str, str, str]


@attrs.define(frozen=True, kw_only=True)
class _Exported:
    service: ServedService
    # The definition and the codec of each method, by name, and what serves its calls.
    methods: dict[str, tuple[Method, MethodCodec, Invoke]]


@attrs.define(frozen=True, kw_only=True)
class _Request:
    """A request read to the end, for an exported service."""

    head: RequestHead
    arguments: tuple[Any, ...]
    attachments: dict[str, Any]
    exported: _Exported


class DubboServer(Resource):
    """Serves the services exported on one address, finding each request's by interface, group and version.

    Entering it starts listening; closing it stops listening and serving
    new calls, waits for the running ones as long as ``shutwait``, ten
    seconds when absent, cancels the rest and closes the connections. A
    connection that cannot write stops reading. With TLS, each handshake
    may take the milliseconds of ``ssl-handshake-timeout``, 10000 when
    absent.

    A two-way call runs for the milliseconds of its ``timeout`` attachment,
    or until its caller leaves; then its handler is cancelled as AnyIO
    cancels, so that what it shields from cancellation finishes first, and a
    call past its timeout is answered with ``SERVER_TIMEOUT``. A request for no exported service or
    method, or whose parameter descriptor matches none, is answered with
    ``SERVICE_NOT_FOUND``; one without the two-way flag gets no response. A
    request beyond the ``max-concurrent-calls`` running at once, 200 when
    absent and any number for 0, is answered with
    ``SERVER_THREADPOOL_EXHAUSTED_ERROR``. Each service also serves the
    `dubbo.protocol.generic.builtin_methods`, such as ``$echo``. The services
    of one interface and version in several groups may declare a method of one
    descriptor with other Python types only if they decode alike.

    Whatever a handler raises is answered with an exception, as
    `dubbo.protocol.java.java_exception` names it; the statuses other than
    OK stand for failures of the server itself. A call that ends with an
    `RpcError` of ``UNAVAILABLE``, as a filter refuses one beyond its limit,
    is answered with ``SERVER_THREADPOOL_EXHAUSTED_ERROR`` too, which
    callers retry on another provider. An invoker that raises
    instead of returning a result is answered with ``SERVICE_ERROR`` and the
    type and message of what it raised.

    Raises:
        ValueError: The URL has no host, or a setting is invalid.
        OSError: A TLS file cannot be read.
    """

    def __init__(self, url: URL, serialization: JavaSerialization, serialization_id: int) -> None:
        if url.host is None:
            raise ValueError(f"a Dubbo server needs a host to listen on: {url}")

        self._host = url.host
        self._port = url.port or 0
        self.shutwait = url.get_parameter(SHUTWAIT_KEY, milliseconds, DEFAULT_SHUTWAIT)
        self._settings = ConnectionSettings.from_url(url)
        self._ssl_context = get_ssl_context(url, server=True)
        self._ssl_handshake_timeout = ssl_handshake_timeout(url)
        self._call_limit = _max_concurrent_calls(url)
        self._serialization = serialization
        self._serialization_id = serialization_id
        self._responses = ResponseCodec(serialization)
        self._events = EventBodies.from_serialization(serialization)
        self._late = self._responses.encode_message("the call ran out of the time its caller gave it")
        self._services: dict[_ServiceKey, _Exported] = {}
        # The codec that reads the arguments of each method, shared by the groups that export it, as the group follows them.
        self._methods: dict[_MethodKey, MethodCodec] = {}
        self._connections: set[DubboConnection] = set()
        self._calls: set[asyncio.Task[None]] = set()
        # The scopes of the running calls that each connection waits to be answered.
        self._answering: dict[DubboConnection, set[anyio.CancelScope]] = {}
        self._listener: asyncio.Server | None = None
        self._address: tuple[str, int] | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._address is None:
            raise RuntimeError("the Dubbo server is not listening")
        return self._address

    def add(self, service: ServedService, definition: Service) -> None:
        """Start serving the methods of ``definition`` with ``service``.

        Raises:
            TypeError: A method is not unary, or the serialization cannot
                carry it.
            ValueError: Another service is exported with the same interface,
                group and version, or with the same interface and version
                and a method of the same name and descriptor but other
                Python parameter types.
        """
        key = (definition.interface, service.group, service.version)
        if key in self._services:
            raise ValueError(f"{service.key} is already exported on {self._host}:{self._port}")

        methods: dict[str, tuple[Method, MethodCodec, Invoke]] = {}
        for method in definition.methods:
            if method.rpc_type is not RpcType.UNARY:
                raise TypeError(f"Dubbo carries unary calls, but {method.name} is {method.rpc_type.value}")
            codec = MethodCodec(self._responses, definition.interface, service.version, method)
            shared = self._methods.get((definition.interface, service.version, method.name, codec.descriptor))
            if shared is not None and shared.parameter_types != codec.parameter_types:
                raise ValueError(
                    f"{definition.interface}.{method.name}({codec.descriptor}) is exported in another group "
                    "with other parameter types"
                )
            methods[method.name] = (method, codec, service.invoker.invoke)
        for method, serve in builtin_methods(definition, service.invoker.invoke, self._serialization):
            codec = MethodCodec(self._responses, definition.interface, service.version, method)
            methods[method.name] = (method, codec, serve)

        self._services[key] = _Exported(service=service, methods=methods)
        self._index()

    def remove(self, service: ServedService) -> None:
        """Stop serving ``service``; its new calls are answered with ``SERVICE_NOT_FOUND``."""
        self._services = {key: exported for key, exported in self._services.items() if exported.service is not service}
        self._index()

    def check(self, url: URL) -> None:
        """Check that ``url`` asks for the serialization and the settings this server runs with.

        Raises:
            ValueError: The serialization, a connection setting or
                ``max-concurrent-calls`` differs.
        """
        asked = (SERIALIZATION_IDS.get(url.parameters.get(SERIALIZATION_KEY, "")), ConnectionSettings.from_url(url))
        if (*asked, _max_concurrent_calls(url)) != (self._serialization_id, self._settings, self._call_limit):
            raise ValueError(
                f"the Dubbo server at {self._host}:{self.address[1]} runs with another serialization or settings"
            )

    def announce_shutdown(self) -> None:
        """Tell every connected consumer that the server stops taking calls, while serving on."""
        for connection in tuple(self._connections):
            connection.announce_shutdown()

    async def aclose(self) -> None:
        listener, self._listener = self._listener, None
        if listener is None:
            return

        listener.close()
        # Calls that arrive from now on find no service, so that their callers try another provider.
        self._services, self._methods = {}, {}
        try:
            await wait_then_cancel(self._calls, self.shutwait)
            async with anyio.create_task_group() as closing:
                for connection in tuple(self._connections):
                    closing.start_soon(connection.aclose)
        except BaseException:
            # Cancelled: the connections still open close at once.
            for connection in tuple(self._connections):
                connection.abort()
            raise
        finally:
            abort_handshakes(listener)
            with release_shield():
                await listener.wait_closed()

    async def __aenter__(self) -> Self:
        listener, address = await create_listener(
            self._create_connection, self._host, self._port, self._ssl_context, self._ssl_handshake_timeout
        )
        try:
            await listener.start_serving()
        except BaseException:
            # No one owns the server until it has started, so a start that fails closes its listener.
            listener.close()
            raise

        self._listener, self._address = listener, address
        return self

    def _index(self) -> None:
        methods: dict[_MethodKey, MethodCodec] = {}
        for (interface, _, version), exported in self._services.items():
            for name, (_, codec, _) in exported.methods.items():
                methods.setdefault((interface, version, name, codec.descriptor), codec)
        self._methods = methods

    def _create_connection(self) -> DubboConnection:
        return DubboConnection(
            on_frame=self._receive,
            on_connected=self._connections.add,
            on_closed=self._connection_closed,
            serialization_id=self._serialization_id,
            events=self._events,
            heartbeat=None,
            idle_timeout=self._settings.idle_timeout,
            max_body=self._settings.max_body,
            pause_reading=True,
        )

    def _connection_closed(self, connection: DubboConnection) -> None:
        self._connections.discard(connection)
        # No one waits for the answers of a caller that left, so its calls end and free their places.
        for scope in self._answering.pop(connection, ()):
            scope.cancel()

    def _receive(self, connection: DubboConnection, flags: int, status: int, request_id: int, body: bytes) -> None:
        if not flags & FLAG_REQUEST:
            return

        two_way = bool(flags & FLAG_TWO_WAY)
        received = flags & SERIALIZATION_MASK
        if received != self._serialization_id:
            message = (
                f"the request is in {_serialization_name(received)}, "
                f"but this server reads {_serialization_name(self._serialization_id)}"
            )
            self._fail(connection, two_way, request_id, ResponseStatus.SERIALIZATION_ERROR, message)
            return
        if self._call_limit and len(self._calls) >= self._call_limit:
            message = f"the server runs {self._call_limit} calls at once, its most"
            self._fail(connection, two_way, request_id, ResponseStatus.SERVER_THREADPOOL_EXHAUSTED_ERROR, message)
            return

        try:
            request = self._read(body)
        except ValueError as error:
            # At debug, as a peer that keeps sending such requests would flood a higher level.
            _logger.debug("Cannot read a request from %s: %s; it is answered with BAD_REQUEST", connection.peer, error)
            self._fail(connection, two_way, request_id, ResponseStatus.BAD_REQUEST, f"cannot read the request: {error}")
            return
        except _NotFound as error:
            self._fail(connection, two_way, request_id, ResponseStatus.SERVICE_NOT_FOUND, str(error))
            return

        loop = asyncio.get_running_loop()
        if two_way:
            timeout = _timeout(request.attachments.get(TIMEOUT_KEY))
            deadline = math.inf if timeout is None else loop.time() + timeout
            serving = self._serve(connection, request_id, request, deadline)
        else:
            serving = self._serve_oneway(connection, request)
        # Nothing between creating the task and tracking it may raise, so that every call has an owner.
        task = loop.create_task(serving)
        self._calls.add(task)
        # For a call cancelled before it starts; one that starts leaves the count as it ends.
        task.add_done_callback(self._calls.discard)
        request.exported.service.track(task)

    def _read(self, body: bytes) -> _Request:
        """Return the request ``body`` holds, reading its arguments as the parameters of the method it names.

        Raises:
            ValueError: The body holds no request, or no arguments of those
                parameters.
            _NotFound: No exported service or method matches the request.
        """
        reader = self._serialization.reader(body)
        head = read_request_head(reader)
        codec = self._methods.get((head.path, head.version, head.method, head.descriptor))
        if codec is None:
            raise _NotFound(
                f"no exported method matches {head.path}.{head.method}({head.descriptor}) (version {head.version!r})"
            )
        arguments, attachments = codec.read_arguments(reader)

        group = attachments.get(GROUP_KEY) or ""
        if not isinstance(group, str):
            raise ValueError(f"the attachment {GROUP_KEY} is no text")
        exported = self._services.get((head.path, group, head.version))
        if exported is None:
            raise _NotFound(f"no exported service matches {head.path} (group {group!r}, version {head.version!r})")
        # The codec read the arguments for any group; the method of this group must take them too.
        method = exported.methods.get(head.method)
        if method is None or method[1].descriptor != head.descriptor:
            raise _NotFound(
                f"{head.path} (group {group!r}, version {head.version!r}) has no method "
                f"{head.method}({head.descriptor})"
            )

        return _Request(head=head, arguments=arguments, attachments=attachments, exported=exported)

    async def _serve(self, connection: DubboConnection, request_id: int, request: _Request, deadline: float) -> None:
        """Run ``request`` and answer it, as a two-way call that ends at ``deadline``."""
        try:
            await self._answer(connection, request_id, request, deadline)
        finally:
            self._done()

    async def _serve_oneway(self, connection: DubboConnection, request: _Request) -> None:
        """Run ``request``, a one-way call, which no one waits to be answered."""
        try:
            await self._outcome(connection, request)
        finally:
            self._done()

    def _done(self) -> None:
        # The call leaves the count at once: its done callback may run only after the next requests are read.
        self._calls.discard(asyncio.current_task())

    async def _answer(self, connection: DubboConnection, request_id: int, request: _Request, deadline: float) -> None:
        # The call ends in a scope at its deadline or when its caller leaves, so that its shields hold. The scope is
        # made in the task: outside one, AnyIO may not tell which event loop runs.
        with anyio.CancelScope(deadline=deadline) as scope:
            answering = self._answering.setdefault(connection, set())
            answering.add(scope)
            try:
                result = await self._outcome(connection, request)
            finally:
                answering.discard(scope)
        if scope.cancelled_caught:
            # Past its timeout, as a caller that left waits for no answer.
            if connection in self._connections:
                connection.write_frame(0, ResponseStatus.SERVER_TIMEOUT, request_id, self._late)
            return

        status, body = self._respond(request, result)
        await connection.wait_writable()
        try:
            connection.write_frame(0, status, request_id, body)
        except ValueError as error:
            message = self._responses.encode_message(str(error))
            connection.write_frame(0, ResponseStatus.BAD_RESPONSE, request_id, message)

    async def _outcome(self, connection: DubboConnection, request: _Request) -> Result | Exception:
        """Return the result of running ``request``, or the exception the method raised instead."""
        try:
            return await self._invoke(connection, request)
        except Exception as error:
            if not isinstance(error, RpcError):
                _logger.exception(
                    "Serving %s.%s raised instead of returning a result; its caller receives the error",
                    request.head.path,
                    request.head.method,
                )
            return error

    async def _invoke(self, connection: DubboConnection, request: _Request) -> Result:
        """Run the method ``request`` names."""
        method, _, invoke = request.exported.methods[request.head.method]
        attachments = to_attachments(request.attachments)
        invocation = Invocation(
            interface=request.head.path,
            method=request.head.method,
            arguments=request.arguments,
            attachments=attachments,
            definition=method,
        )
        with serving(attachments, peer=connection.peer):
            return await invoke(invocation)

    def _respond(self, request: _Request, result: Result | Exception) -> tuple[int, bytes]:
        """Return the status and the body of the response to ``request``, which ended with ``result``."""
        if isinstance(result, Exception):
            return ResponseStatus.SERVICE_ERROR, self._responses.encode_message(f"{type(result).__name__}: {result}")

        error = result.error
        # Refused, as a filter refuses a call beyond its limit: the caller tries another provider.
        if isinstance(error, RpcError) and not isinstance(error, RemoteError) and error.status is Status.UNAVAILABLE:
            return ResponseStatus.SERVER_THREADPOOL_EXHAUSTED_ERROR, self._responses.encode_message(error.message)

        attachments = self._attachments(request.head, result.attachments)
        try:
            if result.error is not None:
                exception = java_exception(self._serialization, result.error)
                return ResponseStatus.OK, self._responses.encode_exception(exception, attachments)
            _, codec, _ = request.exported.methods[request.head.method]
            return ResponseStatus.OK, codec.encode_value(result.value, attachments)
        except (TypeError, ValueError) as encode_error:
            head = request.head
            _logger.warning("Cannot encode the response of %s.%s: %s", head.path, head.method, encode_error)
            return ResponseStatus.BAD_RESPONSE, self._responses.encode_message(
                f"cannot encode the response: {encode_error}"
            )

    def _attachments(self, head: RequestHead, attachments: Any) -> dict[str, Any] | None:
        """Return the attachments a response to ``head`` carries, or ``None`` when its consumer reads none."""
        if not supports_response_attachments(head.dubbo_version):
            return None
        return {**attachments, DUBBO_VERSION_KEY: DUBBO_VERSION}

    def _fail(self, connection: DubboConnection, two_way: bool, request_id: int, status: int, message: str) -> None:
        if two_way:
            connection.write_frame(0, status, request_id, self._responses.encode_message(message))


def _max_concurrent_calls(url: URL) -> int:
    """Return the calls a server of ``url`` runs at once, from ``max-concurrent-calls``; 200 when absent, 0 for any number.

    Raises:
        ValueError: The parameter is negative.
    """
    limit = url.get_parameter(MAX_CONCURRENT_CALLS_KEY, int, DEFAULT_MAX_CONCURRENT_CALLS)
    if limit < 0:
        raise ValueError(f"{MAX_CONCURRENT_CALLS_KEY} must not be negative")
    return limit


def _timeout(value: object) -> float | None:
    """Return the seconds the ``timeout`` attachment ``value`` gives a call, or ``None`` for no positive whole milliseconds."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    try:
        seconds = milliseconds(value)
    except (ValueError, OverflowError):
        return None
    return seconds or None


def _serialization_name(serialization_id: int) -> str:
    """Return the name of the serialization ``serialization_id`` stands for, with the id."""
    names = [name for name, value in SERIALIZATION_IDS.items() if value == serialization_id]
    return f"{names[0]} ({serialization_id})" if names else f"serialization {serialization_id}"


class _NotFound(Exception):
    """No exported service or method matches a request."""
