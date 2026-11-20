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

import gzip
from collections.abc import Awaitable, Callable

import pytest

from dubbo import RpcError, Status
from dubbo.constants import DEFAULT_MAX_RECEIVE_MESSAGE_SIZE
from dubbo.protocol.triple.grpc.compression import Compressors
from dubbo.protocol.triple.grpc.framing import frame, read_message
from dubbo.url import URL

pytestmark = pytest.mark.anyio


class _Sent:
    """The receiving side of a stream on which the peer sent ``data`` and ended."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def receive_data_exactly(self, nbytes: int) -> bytes:
        chunk, self._data = self._data[:nbytes], self._data[nbytes:]
        return chunk


def _reader(data: bytes, encoding: bytes | None = None) -> Callable[[], Awaitable[bytes | None]]:
    """Return a function that reads the next message of a stream on which the peer sent ``data``."""
    sent = _Sent(data)
    compressor = Compressors(URL(protocol="tri")).get(encoding)
    return lambda: read_message(sent, DEFAULT_MAX_RECEIVE_MESSAGE_SIZE, compressor)  # ty: ignore[invalid-argument-type]


def _compressed(message: bytes) -> bytes:
    data = gzip.compress(message)
    return b"\x01" + len(data).to_bytes(4, "big") + data


def test_frame_prefixes_the_flag_and_big_endian_length() -> None:
    assert frame(b"abc") == b"\x00\x00\x00\x00\x03abc"
    assert frame(b"") == b"\x00\x00\x00\x00\x00"


async def test_frame_compresses_with_a_compressor() -> None:
    compressor = Compressors(URL(protocol="tri")).get(b"gzip")

    framed = frame(b"abc", compressor)

    assert framed[0] == 1
    assert int.from_bytes(framed[1:5], "big") == len(framed) - 5
    assert await _reader(framed, b"gzip")() == b"abc"


async def test_a_stream_receives_messages_until_the_peer_ends() -> None:
    read = _reader(frame(b"a") + frame(b"") + _compressed(b"b"), b"gzip")

    assert [await read() for _ in range(3)] == [b"a", b"", b"b"]
    assert await read() is None


@pytest.mark.parametrize(
    ("data", "encoding", "status", "message"),
    [
        (b"\x00\x00", None, Status.INTERNAL, "inside a message prefix"),
        (frame(b"abc")[:-1], None, Status.INTERNAL, "inside a message"),
        (
            b"\x00" + (DEFAULT_MAX_RECEIVE_MESSAGE_SIZE + 1).to_bytes(4, "big"),
            None,
            Status.RESOURCE_EXHAUSTED,
            "larger than",
        ),
        (b"\x02\x00\x00\x00\x00", None, Status.INTERNAL, "invalid compressed flag 2"),
        # PROTOCOL-HTTP2.md:98; compression.md:105
        (_compressed(b"a"), None, Status.INTERNAL, "without grpc-encoding"),
        (b"\x01\x00\x00\x00\x01x", b"gzip", Status.INTERNAL, "cannot decompress"),
        (
            _compressed(b"\0" * (DEFAULT_MAX_RECEIVE_MESSAGE_SIZE + 1)),
            b"gzip",
            Status.RESOURCE_EXHAUSTED,
            "decompressed message",
        ),
    ],
)
async def test_a_stream_rejects_broken_messages(
    data: bytes, encoding: bytes | None, status: Status, message: str
) -> None:
    with pytest.raises(RpcError, match=message) as caught:
        await _reader(data, encoding)()

    assert caught.value.status is status
