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

"""The attachments of a Triple call, which travel as header fields."""

import binascii
import json
import re
from collections.abc import Mapping

from multidict import MultiDict

from dubbo.transport.h2 import H2Header, H2Headers

from .headers import HttpHeader, TripleHeader, decode_binary, encode_binary, percent_decode, percent_encode

__all__ = ["attachment_headers", "split_headers"]

# Fields the call itself uses; every other field is an attachment.
_RESERVED = frozenset({*HttpHeader, *TripleHeader})
_RESERVED_PREFIXES = (b":", b"grpc-")
_ATTACHMENT_KEY = re.compile(r"[0-9a-z_.-]+")
_BINARY_SUFFIX = "-bin"


def split_headers(headers: H2Headers) -> tuple[dict[bytes, bytes], MultiDict[str | bytes]]:
    """Split a field section into the fields the call uses and its attachments, keeping every value of a key.

    An attachment whose key ends with ``-bin`` is bytes, decoded from base64,
    with each of comma-joined values taken apart; a value that is not valid
    base64 is dropped. Attachment keys regain the case that
    ``tri-header-convert`` records.
    """
    fields: dict[bytes, bytes] = {}
    attachments: MultiDict[str | bytes] = MultiDict()
    for name, value in headers:
        if name in _RESERVED or name.startswith(_RESERVED_PREFIXES):
            fields[name] = value
            continue

        key = name.decode("latin-1")
        if not key.endswith(_BINARY_SUFFIX):
            attachments.add(key, value.decode("utf-8", "replace"))
            continue

        for part in value.split(b","):
            encoded = part.strip()
            try:
                attachments.add(key, decode_binary(encoded))
            except binascii.Error:
                continue

    converted = fields.get(TripleHeader.HEADER_CONVERT)
    if converted is not None:
        _restore_case(attachments, converted)

    return fields, attachments


def attachment_headers(attachments: Mapping[str, str | bytes]) -> list[H2Header]:
    """Return the fields that carry ``attachments``, recording upper-case keys in ``tri-header-convert``.

    Each value of a key is a field of its own. A key ending with ``-bin``
    takes bytes, sent as base64 without padding; every other key takes
    printable ASCII text.

    Raises:
        ValueError: A key is not a valid field name, is reserved, or differs
            from another only in case, or a value does not suit its key.
    """
    headers: list[H2Header] = []
    converted: dict[str, str] = {}
    for key, value in attachments.items():
        name = key.lower()
        encoded = name.encode("ascii", "replace")
        if not _ATTACHMENT_KEY.fullmatch(name) or encoded in _RESERVED or encoded.startswith(_RESERVED_PREFIXES):
            raise ValueError(f"attachment key {key!r} cannot be a gRPC metadata name")
        if name.endswith(_BINARY_SUFFIX):
            if not isinstance(value, bytes):
                raise ValueError(f"attachment {key!r} ends with {_BINARY_SUFFIX!r} and must be bytes")
            data = encode_binary(value)
        elif isinstance(value, str) and value.isascii() and value.isprintable():
            data = value.encode("ascii")
        else:
            raise ValueError(f"attachment {key!r} must be printable ASCII text")
        if name != key and (converted.setdefault(name, key) != key or name in attachments):
            raise ValueError(f"attachment keys differ only in case: {key!r}")

        headers.append((encoded, data))

    if converted:
        headers.append((TripleHeader.HEADER_CONVERT, percent_encode(json.dumps(converted, separators=(",", ":")))))

    return headers


def _restore_case(attachments: MultiDict[str | bytes], converted: bytes) -> None:
    try:
        keys = json.loads(percent_decode(converted))
    except ValueError:
        return

    if isinstance(keys, dict):
        for name, key in keys.items():
            if isinstance(key, str) and name in attachments:
                attachments.extend((key, value) for value in attachments.popall(name))
