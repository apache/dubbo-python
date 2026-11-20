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

"""The HTTP and Triple header fields of a call, and the encodings of their values."""

import base64
import enum
from http import HTTPStatus
from urllib.parse import quote, unquote

__all__ = [
    "HTTP_OK",
    "HttpHeader",
    "TripleHeader",
    "decode_binary",
    "encode_binary",
    "percent_decode",
    "percent_encode",
]

# The :status of every successful response.
HTTP_OK = b"%d" % HTTPStatus.OK

# Printable ASCII except "%", the characters percent-encoding leaves as they are.
_PERCENT_SAFE = "".join(chr(code) for code in range(0x20, 0x7F) if chr(code) != "%")


class HttpHeader(bytes, enum.Enum):
    """HTTP fields of a call."""

    METHOD = b":method"
    SCHEME = b":scheme"
    AUTHORITY = b":authority"
    PATH = b":path"
    STATUS = b":status"
    CONTENT_TYPE = b"content-type"
    CONTENT_LENGTH = b"content-length"
    TE = b"te"
    USER_AGENT = b"user-agent"


class TripleHeader(bytes, enum.Enum):
    """Fields of Triple beyond gRPC: the service called, the caller, and an exception a response holds."""

    SERVICE_GROUP = b"tri-service-group"
    SERVICE_VERSION = b"tri-service-version"
    CONSUMER_APPLICATION = b"tri-consumer-appname"
    HEADER_CONVERT = b"tri-header-convert"
    # Other than 0 when the response message is an exception the method threw.
    EXCEPTION_CODE = b"tri-exception-code"


def percent_encode(text: str) -> bytes:
    """Percent-encode every character of ``text`` that is not printable ASCII, and ``%``."""
    return quote(text, safe=_PERCENT_SAFE).encode("ascii")


def percent_decode(value: bytes) -> str:
    """Decode a percent-encoded value, keeping malformed escapes as they are."""
    return unquote(value.decode("utf-8", "replace"), errors="replace")


def encode_binary(data: bytes) -> bytes:
    """Return the value of a ``-bin`` field that carries ``data``: base64 without padding."""
    return base64.b64encode(data).rstrip(b"=")


def decode_binary(value: bytes) -> bytes:
    """Return the bytes the value of a ``-bin`` field carries, padded or not.

    Raises:
        binascii.Error: The value is no base64.
    """
    return base64.b64decode(value + b"=" * (-len(value) % 4), validate=True)
