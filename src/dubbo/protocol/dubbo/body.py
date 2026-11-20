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

"""The bodies of Dubbo requests and responses: which values they hold, in which order."""

import enum
import functools
import logging
from collections.abc import Mapping
from typing import Any

import attrs
from multidict import MultiDict

from dubbo.constants import DUBBO_VERSION
from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.protocol.java import method_descriptor
from dubbo.rpc.definition import Method
from dubbo.serialization import JavaSerialization, Reader
from dubbo.utils.converters import to_text

__all__ = [
    "MethodCodec",
    "RequestHead",
    "Response",
    "ResponseCodec",
    "ResponseStatus",
    "read_request_head",
    "service_version",
    "status_error",
    "supports_response_attachments",
    "to_attachments",
]

_logger = logging.getLogger(__name__)

# The version a request carries for a service without one, and those that mean none.
_NO_VERSION = "0.0.0"
_NO_VERSIONS = frozenset({"", _NO_VERSION, "*"})
# The protocol version, interface, service version, method and descriptor that start a request.
_HEAD = (str, str, str | None, str, str)
_ATTACHMENTS = dict[str, Any]
# The kinds of response bodies, as the first value of each.
_EXCEPTION, _VALUE, _NULL = 0, 1, 2
_WITH_ATTACHMENTS = 3  # Added to a kind whose body ends with attachments.
# The consumer versions that read response attachments: 2.0.2 to 2.0.99.
_ATTACHMENT_VERSIONS = ((2, 0, 2, 0), (2, 0, 99, 0))
# The types of the attachments kept as they are, and of those that become text.
_TEXT = (str, bytes)
_SCALARS = (bool, int, float)


class ResponseStatus(enum.IntEnum):
    """The status byte of a response header.

    Every status but `OK` has a body of one string, the error message.
    """

    OK = 20  # The body holds the result.
    SERIALIZATION_ERROR = 25  # The request or the result cannot be serialized.
    CLIENT_TIMEOUT = 30  # The consumer gave up waiting.
    SERVER_TIMEOUT = 31  # The provider gave up running the call.
    CHANNEL_INACTIVE = 35  # The connection closed before the response arrived.
    BAD_REQUEST = 40  # The request cannot be read.
    BAD_RESPONSE = 50  # The response cannot be written.
    SERVICE_NOT_FOUND = 60  # No exported service or method matches the request.
    SERVICE_ERROR = 70  # The service failed outside its result.
    SERVER_ERROR = 80  # The provider failed.
    CLIENT_ERROR = 90  # The consumer failed.
    SERVER_THREADPOOL_EXHAUSTED_ERROR = 100  # The provider has no room for another call.


_STATUS_ERRORS: dict[int, Status] = {
    ResponseStatus.CLIENT_TIMEOUT: Status.DEADLINE_EXCEEDED,
    ResponseStatus.SERVER_TIMEOUT: Status.DEADLINE_EXCEEDED,
    ResponseStatus.CHANNEL_INACTIVE: Status.UNAVAILABLE,
    ResponseStatus.BAD_REQUEST: Status.INVALID_ARGUMENT,
    # The provider runs no such service, as while it goes offline; another may.
    ResponseStatus.SERVICE_NOT_FOUND: Status.UNAVAILABLE,
    # The provider has no room for the call; another may.
    ResponseStatus.SERVER_THREADPOOL_EXHAUSTED_ERROR: Status.UNAVAILABLE,
    ResponseStatus.SERIALIZATION_ERROR: Status.INTERNAL,
    ResponseStatus.SERVICE_ERROR: Status.INTERNAL,
    ResponseStatus.BAD_RESPONSE: Status.INTERNAL,
    ResponseStatus.CLIENT_ERROR: Status.INTERNAL,
}


@attrs.define(frozen=True, kw_only=True)
class RequestHead:
    """The values that start a request and name the method it calls.

    Attributes:
        dubbo_version: Version of the protocol model the consumer speaks.
        path: Interface of the service called.
        version: Version of the service called; empty when it has none.
        method: Name of the method called.
        descriptor: Java descriptor of the parameters, such as ``J``.
    """

    dubbo_version: str
    path: str
    version: str
    method: str
    descriptor: str


@attrs.define(frozen=True, kw_only=True)
class Response:
    """A response as a consumer reads it.

    Attributes:
        value: What the method returned; ``None`` for nothing or a failure.
        exception: The exception the method raised; ``None`` when it
            returned.
        attachments: What the provider attached.
    """

    value: Any = None
    exception: RemoteError | None = None
    attachments: Mapping[str, Any] = attrs.field(factory=dict)


class ResponseCodec:
    """Writes and reads the responses of one serialization that do not depend on the method: errors, nulls and exceptions."""

    def __init__(self, serialization: JavaSerialization) -> None:
        self.serialization = serialization
        self._message = serialization.codec((str,))
        self._null = serialization.codec((int,))
        self._null_attached = serialization.codec((int, _ATTACHMENTS))
        self._exception = serialization.codec((int, Exception))
        self._exception_attached = serialization.codec((int, Exception, _ATTACHMENTS))

    def encode_message(self, message: str) -> bytes:
        """Return the body of a response with a status other than OK."""
        return self._message.encode((message,))

    def decode_message(self, data: bytes) -> str:
        """Return the message of a response with a status other than OK.

        Raises:
            ValueError: ``data`` holds no message.
        """
        return self.serialization.reader(data).load(str)

    def encode_null(self, attachments: Mapping[str, Any] | None) -> bytes:
        if attachments is None:
            return self._null.encode((_NULL,))
        return self._null_attached.encode((_NULL + _WITH_ATTACHMENTS, attachments))

    def encode_exception(self, exception: Exception, attachments: Mapping[str, Any] | None) -> bytes:
        """Return the body of a response with ``exception``, a `RemoteError` or one of a class the serialization declares."""
        if attachments is None:
            return self._exception.encode((_EXCEPTION, exception))
        return self._exception_attached.encode((_EXCEPTION + _WITH_ATTACHMENTS, exception, attachments))

    def decode_response(self, data: bytes, value_type: Any = Any) -> Response:
        """Return the response ``data`` holds, its value decoded as ``value_type``.

        Values after the response, such as the null some providers append,
        are left unread.

        Raises:
            ValueError: ``data`` holds no response.
        """
        reader = self.serialization.reader(data)
        kind = reader.load(int)
        if not 0 <= kind <= _NULL + _WITH_ATTACHMENTS:
            raise ValueError(
                f"the body is not a Dubbo response, whose kind is {_EXCEPTION} to {_NULL + _WITH_ATTACHMENTS}"
            )

        attached = kind >= _WITH_ATTACHMENTS
        kind -= _WITH_ATTACHMENTS if attached else 0
        value = exception = None
        if kind == _VALUE:
            value = reader.load(value_type)
        elif kind == _EXCEPTION:
            exception = reader.load(Exception)
        attachments = reader.load(_ATTACHMENTS) if attached else {}
        return Response(value=value, exception=exception, attachments=attachments)


class MethodCodec:
    """Writes and reads the bodies of the calls of one method of a service, made once for each method.

    Raises:
        TypeError: The serialization cannot carry the parameters or the
            response of ``method``, or a parameter has no Java type.
    """

    def __init__(self, responses: ResponseCodec, path: str, version: str, method: Method) -> None:
        serialization = responses.serialization
        self.descriptor = method_descriptor(serialization, method)
        self.parameter_types = tuple(parameter.type for parameter in method.request)
        self._responses = responses
        self._prefix = (DUBBO_VERSION, path, version or _NO_VERSION, method.name, self.descriptor)
        self._request = serialization.codec((str, str, str, str, str, *self.parameter_types, _ATTACHMENTS))
        # A method that returns nothing answers with a null response.
        self._response_type = method.response
        self._null_error: str | None = None
        if method.response is not None:
            self._value = serialization.codec((int, method.response))
            self._value_attached = serialization.codec((int, method.response, _ATTACHMENTS))
            if not _decodes_null(serialization, method.response):
                name = getattr(method.response, "__qualname__", None) or repr(method.response)
                self._null_error = f"the provider returned null, which {name} does not allow; declare {name} | None"

    def encode_request(self, arguments: tuple[Any, ...], attachments: Mapping[str, Any]) -> bytes:
        return self._request.encode((*self._prefix, *arguments, attachments))

    def read_arguments(self, reader: Reader) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Return the arguments and the attachments of a request, after its head.

        Raises:
            ValueError: The rest of the request holds no arguments of the
                parameter types and attachments.
        """
        arguments = tuple(reader.load(annotation) for annotation in self.parameter_types)
        return arguments, reader.load(_ATTACHMENTS)

    def encode_value(self, value: Any, attachments: Mapping[str, Any] | None) -> bytes:
        """Return the body of a response with ``value``, ending with ``attachments`` unless they are ``None``."""
        if value is None or self._response_type is None:
            return self._responses.encode_null(attachments)
        if attachments is None:
            return self._value.encode((_VALUE, value))
        return self._value_attached.encode((_VALUE + _WITH_ATTACHMENTS, value, attachments))

    def decode_response(self, data: bytes) -> Response:
        """Return the response ``data`` holds, its value of the method's return type.

        Raises:
            ValueError: ``data`` holds no response of this method, or a null
                value the return type does not allow, such as ``User``
                without ``| None``.
        """
        response = self._responses.decode_response(data, Any if self._response_type is None else self._response_type)
        if response.value is None and response.exception is None and self._null_error is not None:
            raise ValueError(self._null_error)
        return response


def read_request_head(reader: Reader) -> RequestHead:
    """Return the head of a request, the values before its arguments.

    Raises:
        ValueError: The request starts with no head.
    """
    dubbo_version, path, version, method, descriptor = (reader.load(annotation) for annotation in _HEAD)
    return RequestHead(
        dubbo_version=dubbo_version,
        path=path,
        version=service_version(version),
        method=method,
        descriptor=descriptor,
    )


def service_version(version: str | None) -> str:
    """Return the version of a service as a request names it: empty for none, as ``0.0.0`` and ``*`` say too."""
    return "" if version is None or version in _NO_VERSIONS else version


# Bounded, since the versions come from the peers.
@functools.lru_cache(maxsize=64)
def supports_response_attachments(dubbo_version: str) -> bool:
    """Return whether a consumer of ``dubbo_version`` reads attachments at the end of a response."""
    try:
        parts = tuple(int(part) for part in dubbo_version.split("."))
    except ValueError:
        return False

    lowest, highest = _ATTACHMENT_VERSIONS
    return lowest <= (*parts, 0, 0, 0, 0)[:4] <= highest


def status_error(status: int, message: str) -> RpcError:
    """Return the error a consumer receives for a response with a status other than OK."""
    try:
        name = ResponseStatus(status).name
    except ValueError:
        name = str(status)
    rpc_status = _STATUS_ERRORS.get(status, Status.UNKNOWN)
    return RpcError(rpc_status, f"{name}: {message}" if message else name)


def to_attachments(values: Mapping[str, Any]) -> MultiDict[str | bytes]:
    """Return the attachments a call carries in Python for those it received.

    Text and bytes stay as they are, numbers and booleans become text, and
    values of other types are left out.
    """
    attachments: MultiDict[str | bytes] = MultiDict()
    for key, value in values.items():
        if isinstance(value, _TEXT):
            attachments[key] = value
        elif isinstance(value, _SCALARS):
            attachments[key] = to_text(value)
        else:
            _logger.debug("Cannot read the attachment %s of type %s; it is left out", key, type(value).__name__)

    return attachments


def _decodes_null(serialization: JavaSerialization, annotation: Any) -> bool:
    """Return whether a null of ``serialization`` reads as ``annotation``."""
    null = serialization.codec((None,)).encode((None,))
    try:
        serialization.reader(null).load(annotation)
    except ValueError:
        return False
    return True
