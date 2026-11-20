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

"""The length-prefixed messages of a gRPC call on an HTTP/2 stream."""

import struct

from dubbo.compression import Compressor
from dubbo.exceptions import RpcError, Status
from dubbo.transport.h2 import H2Stream

__all__ = ["frame", "read_message"]

_PREFIX = struct.Struct(">BI")
_UNCOMPRESSED = 0
_COMPRESSED = 1


def frame(message: bytes, compressor: Compressor | None = None) -> bytes:
    """Prefix a message with its flag and length, compressing it first with ``compressor`` when there is one."""
    if compressor is None:
        return _PREFIX.pack(_UNCOMPRESSED, len(message)) + message

    message = compressor.compress(message)
    return _PREFIX.pack(_COMPRESSED, len(message)) + message


async def read_message(stream: H2Stream, max_size: int, compressor: Compressor | None) -> bytes | None:
    """Return the next message of ``stream``, or ``None`` once the peer has sent its last.

    ``compressor`` is the one the peer's grpc-encoding names.

    Raises:
        RpcError: The message is cut short, larger than ``max_size`` bytes or
            wrongly compressed.
        H2Error: The stream failed.
    """
    prefix = await stream.receive_data_exactly(_PREFIX.size)
    if len(prefix) < _PREFIX.size:
        if prefix:
            raise RpcError(Status.INTERNAL, "the stream ended inside a message prefix")
        return None

    flag, length = _PREFIX.unpack(prefix)
    if length > max_size:
        raise RpcError(Status.RESOURCE_EXHAUSTED, f"message of {length} bytes is larger than {max_size}")

    message = await stream.receive_data_exactly(length)
    if len(message) < length:
        raise RpcError(Status.INTERNAL, "the stream ended inside a message")

    if flag == _UNCOMPRESSED:
        return message
    if flag == _COMPRESSED:
        return _decompress(message, max_size, compressor)
    raise RpcError(Status.INTERNAL, f"invalid compressed flag {flag}")


def _decompress(message: bytes, max_size: int, compressor: Compressor | None) -> bytes:
    if compressor is None:
        raise RpcError(Status.INTERNAL, "compressed message without grpc-encoding")

    try:
        message = compressor.decompress(message, max_size + 1)
    except ValueError as error:
        raise RpcError(Status.INTERNAL, f"cannot decompress the message: {error}") from None

    if len(message) > max_size:
        raise RpcError(Status.RESOURCE_EXHAUSTED, f"decompressed message is larger than {max_size}")
    return message
