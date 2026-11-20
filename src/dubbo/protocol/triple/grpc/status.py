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

"""The statuses that end a gRPC call, and the errors of responses and transports that stand for one."""

from collections.abc import Mapping
from http import HTTPStatus

from google.protobuf.message import DecodeError

from dubbo._proto.google.rpc.status_pb2 import Status as StatusMessage
from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.transport.h2 import H2ConnectionError, H2Error, H2ErrorCode, H2Header, H2StreamResetError

from ..exceptions import ErrorDetail, TripleError
from ..headers import HTTP_OK, HttpHeader, decode_binary, encode_binary, percent_decode, percent_encode
from .headers import GrpcHeader, content_subtype

__all__ = ["response_error", "status_headers", "to_rpc_error", "trailer_error", "transport_error"]

_GRPC_OK = b"%d" % Status.OK
_HTTP_STATUSES = {
    HTTPStatus.BAD_REQUEST: Status.INTERNAL,
    HTTPStatus.UNAUTHORIZED: Status.UNAUTHENTICATED,
    HTTPStatus.FORBIDDEN: Status.PERMISSION_DENIED,
    HTTPStatus.NOT_FOUND: Status.UNIMPLEMENTED,
    HTTPStatus.TOO_MANY_REQUESTS: Status.UNAVAILABLE,
    HTTPStatus.BAD_GATEWAY: Status.UNAVAILABLE,
    HTTPStatus.SERVICE_UNAVAILABLE: Status.UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT: Status.UNAVAILABLE,
}
_RESET_STATUSES = {
    H2ErrorCode.REFUSED_STREAM: Status.UNAVAILABLE,
    H2ErrorCode.CANCEL: Status.CANCELLED,
    H2ErrorCode.ENHANCE_YOUR_CALM: Status.RESOURCE_EXHAUSTED,
    H2ErrorCode.INADEQUATE_SECURITY: Status.PERMISSION_DENIED,
}


def status_headers(error: RpcError | None) -> list[H2Header]:
    """Return the grpc-status, grpc-message and grpc-status-details-bin fields that end a call."""
    if error is None:
        return [(GrpcHeader.STATUS, _GRPC_OK)]

    headers = [(GrpcHeader.STATUS, b"%d" % error.status)]
    if error.message:
        headers.append((GrpcHeader.MESSAGE, percent_encode(error.message)))
    if isinstance(error, TripleError) and error.details:
        headers.append((GrpcHeader.STATUS_DETAILS, _encode_details(error)))
    return headers


def response_error(fields: Mapping[bytes, bytes]) -> RpcError | None:
    """Return why response headers are not those of a gRPC response, if they are not."""
    value = fields.get(HttpHeader.STATUS)
    if value != HTTP_OK:
        code = int(value) if value is not None and value.isdigit() else 0
        return RpcError(_HTTP_STATUSES.get(code, Status.UNKNOWN), f"unexpected HTTP status {code}")

    value = fields.get(HttpHeader.CONTENT_TYPE)
    if content_subtype(value) is None:
        return RpcError(Status.UNKNOWN, f"unexpected content-type {value!r}")

    return None


def trailer_error(fields: Mapping[bytes, bytes]) -> RpcError | None:
    """Return the error that ending fields report; ``None`` for OK."""
    # OK comes first: almost every call ends with it.
    value = fields.get(GrpcHeader.STATUS)
    if value == _GRPC_OK:
        return None
    if value is None:
        return RpcError(Status.UNKNOWN, "the server sent no grpc-status")
    try:
        # int() also refuses digits past the limit of its conversion.
        code = int(value) if value.isdigit() else None
    except ValueError:
        code = None
    if code is None:
        return RpcError(Status.INTERNAL, f"malformed grpc-status {value!r}")
    try:
        status = Status(code)
    except ValueError:
        status = Status.UNKNOWN

    message = percent_decode(fields.get(GrpcHeader.MESSAGE, b""))
    encoded = fields.get(GrpcHeader.STATUS_DETAILS)
    decoded = _decode_details(encoded) if encoded is not None else None
    if decoded is None:
        return RpcError(status, message)

    # PROTOCOL-HTTP2.md: the details must not contradict grpc-status, and the consumer verifies it.
    if decoded.code != code:
        return RpcError(
            Status.INTERNAL, f"grpc-status-details-bin has code {decoded.code} but grpc-status is {code}: {message}"
        )
    return TripleError(status, message, details=_details(decoded))


def to_rpc_error(error: Exception) -> RpcError:
    """Return a fresh `RpcError` with the status, message and details of ``error``, without its traceback.

    A `RemoteError` keeps its class in the message.
    """
    if isinstance(error, TripleError):
        return TripleError(error.status, error.message, details=error.details)
    if isinstance(error, RemoteError):
        return RpcError(error.status, str(error))
    if isinstance(error, RpcError):
        return RpcError(error.status, error.message)

    return RpcError(Status.UNKNOWN, f"{type(error).__name__}: {error}")


def transport_error(error: H2Error) -> RpcError:
    """Return the error a call ends with when its HTTP/2 stream or connection fails."""
    if isinstance(error, H2StreamResetError):
        return RpcError(_RESET_STATUSES.get(error.error_code, Status.INTERNAL), str(error))
    if isinstance(error, H2ConnectionError):
        return RpcError(Status.UNAVAILABLE, str(error))
    return RpcError(Status.INTERNAL, str(error))


def _encode_details(error: TripleError) -> bytes:
    """Encode the google.rpc.Status of ``error`` as a binary field value: base64 without padding."""
    status = StatusMessage(code=error.status, message=error.message)
    for detail in error.details:
        status.details.add(type_url=detail.type_url, value=detail.value)

    return encode_binary(status.SerializeToString())


def _decode_details(value: bytes) -> StatusMessage | None:
    """Return the google.rpc.Status a binary field value encodes; ``None`` when it is malformed."""
    try:
        return StatusMessage.FromString(decode_binary(value))
    except (ValueError, DecodeError):
        return None


def _details(status: "StatusMessage") -> tuple[ErrorDetail, ...]:
    return tuple(ErrorDetail(type_url=detail.type_url, value=detail.value) for detail in status.details)
