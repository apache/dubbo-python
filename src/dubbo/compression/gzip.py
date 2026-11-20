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

import zlib

from dubbo.url import URL

from .base import Compressor, bounded_decompress

__all__ = ["GzipCompressor"]

_WBITS = zlib.MAX_WBITS | 16
_CHUNK = 16 * 1024  # Bytes of input given at a time after the first member.


class GzipCompressor(Compressor):
    """Compress messages in the gzip format."""

    def __init__(self, url: URL) -> None:
        pass

    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, wbits=_WBITS)

    def decompress(self, data: bytes, max_length: int) -> bytes:
        decompressor = zlib.decompressobj(_WBITS)
        result = bounded_decompress(decompressor, data, max_length)
        if not decompressor.unused_data or len(result) >= max_length:
            return result

        # A gzip message is a sequence of members that share the one limit. The members after the first get the
        # input in chunks, so that the copy zlib makes of the input left after each member stays short.
        rest, offset, pieces, length = memoryview(decompressor.unused_data), 0, [result], len(result)
        try:
            while offset < len(rest) and length < max_length:
                decompressor = zlib.decompressobj(_WBITS)
                while not decompressor.eof and offset < len(rest) and length < max_length:
                    chunk = rest[offset : offset + _CHUNK]
                    pieces.append(decompressor.decompress(chunk, max_length - length))
                    length += len(pieces[-1])
                    offset += len(chunk) - len(decompressor.unconsumed_tail) - len(decompressor.unused_data)
                if not decompressor.eof and length < max_length:
                    raise ValueError("compressed data is cut short")
        except zlib.error as error:
            raise ValueError(f"malformed compressed data: {error}") from None

        return b"".join(pieces)
