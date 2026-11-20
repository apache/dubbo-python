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

"""The header fields of the gRPC format and the values they carry."""

import enum
import math
import re

__all__ = ["CONTENT_TYPE", "GrpcHeader", "content_subtype", "content_type", "decode_timeout", "encode_timeout"]

CONTENT_TYPE = b"application/grpc"

_TIMEOUT = re.compile(rb"([0-9]{1,8})([HMSmun])")
_TIMEOUT_MAX = 99_999_999
_TIMEOUT_UNITS = {b"H": 3600.0, b"M": 60.0, b"S": 1.0, b"m": 1e-3, b"u": 1e-6, b"n": 1e-9}
# Units from the finest, each with how many make a second.
_TIMEOUT_ENCODINGS = ((b"n", 1e9), (b"u", 1e6), (b"m", 1e3), (b"S", 1.0), (b"M", 1 / 60), (b"H", 1 / 3600))


class GrpcHeader(bytes, enum.Enum):
    """Fields of the gRPC format."""

    TIMEOUT = b"grpc-timeout"
    ENCODING = b"grpc-encoding"
    ACCEPT_ENCODING = b"grpc-accept-encoding"
    STATUS = b"grpc-status"
    MESSAGE = b"grpc-message"
    STATUS_DETAILS = b"grpc-status-details-bin"


def content_type(subtype: str) -> bytes:
    """Return the gRPC content type of messages in the format ``subtype`` names."""
    return CONTENT_TYPE + b"+" + subtype.encode("ascii")


def content_subtype(value: bytes | None) -> bytes | None:
    """Return the subtype of a gRPC content type, ``b""`` when it has none, or ``None`` for another type."""
    if value is None or not value.startswith(CONTENT_TYPE):
        return None

    rest = value[len(CONTENT_TYPE) :]
    if not rest or rest.startswith(b";"):
        return b""
    if not rest.startswith(b"+"):
        return None
    return rest[1:].partition(b";")[0]


def encode_timeout(seconds: float) -> bytes:
    """Encode a positive timeout in the finest unit that fits eight digits, rounding up."""
    for unit, per_second in _TIMEOUT_ENCODINGS:
        value = math.ceil(seconds * per_second)
        if value <= _TIMEOUT_MAX:
            return b"%d%s" % (value, unit)

    return b"%dH" % _TIMEOUT_MAX


def decode_timeout(value: bytes) -> float:
    """Return the seconds a grpc-timeout stands for.

    Raises:
        ValueError: The value is malformed.
    """
    match = _TIMEOUT.fullmatch(value)
    if match is None:
        raise ValueError(f"malformed grpc-timeout {value!r}")
    return int(match[1]) * _TIMEOUT_UNITS[match[2]]
