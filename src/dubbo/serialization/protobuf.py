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

from collections.abc import Sequence
from typing import Any

from google.protobuf.message import DecodeError, Message

from dubbo.url import URL

from .base import Codec, Serialization

__all__ = ["ProtobufSerialization"]

_PYTHON_TYPES = (
    "set the serialization to hessian2, or use the dubbo protocol, to carry Python types and several parameters"
)


class ProtobufSerialization(Serialization):
    """Carry protobuf messages: the bytes hold exactly one message of a known type."""

    content_subtype = "proto"
    shared = True

    def __init__(self, url: URL) -> None:
        pass

    def codec(self, types: Sequence[Any]) -> Codec[tuple[Any, ...]]:
        if len(types) != 1:
            raise TypeError(f"protobuf carries one message of a known type, not {types!r}; {_PYTHON_TYPES}")

        message_type = _message_type(types[0])

        def encode(values: tuple[Any, ...]) -> bytes:
            return _encode(message_type, values[0])

        def decode(data: bytes) -> tuple[Any, ...]:
            return (_decode(message_type, data),)

        return Codec(encode=encode, decode=decode)


def _message_type(annotation: Any) -> type[Message]:
    if not (isinstance(annotation, type) and issubclass(annotation, Message)):
        raise TypeError(f"protobuf carries messages, not {annotation!r}; {_PYTHON_TYPES}")
    return annotation


def _encode(message_type: type[Message], message: Any) -> bytes:
    # SerializeToString accepts a message of any type, so check it first.
    if not isinstance(message, message_type):
        raise TypeError(f"expected {message_type.__qualname__}, not {type(message).__qualname__}")
    return message.SerializeToString()


def _decode(message_type: type[Message], data: bytes) -> Message:
    try:
        return message_type.FromString(data)
    except DecodeError as error:
        raise ValueError(f"not a {message_type.__qualname__}: {error}") from None
