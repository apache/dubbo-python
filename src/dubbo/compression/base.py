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

import typing
import zlib

from dubbo.extension import extension_point, extensions
from dubbo.url import URL

__all__ = ["Compressor", "bounded_decompress", "get_compressor"]


@extension_point("apache_dubbo.compression")
class Compressor(typing.Protocol):
    """A message compression, named by the encoding it travels as, such as ``gzip``.

    Implement ``__init__(url)``, ``compress`` and ``decompress``, and install
    it under the entry point group ``apache_dubbo.compression``, named by its
    encoding. Every installed compressor is offered in
    ``grpc-accept-encoding``; the ``compressor`` parameter picks the one a
    side sends with. A Triple server or client creates one with its URL on
    first use and keeps it. Both methods run in the event loop for every
    message, so they must be quick. The encoding ``identity`` leaves messages
    as they are and has no implementation.
    """

    def __init__(self, url: URL) -> None: ...

    def compress(self, data: bytes) -> bytes:
        """Return ``data`` compressed."""
        ...

    def decompress(self, data: bytes, max_length: int) -> bytes:
        """Return ``data`` decompressed, or only its first ``max_length`` bytes when it is longer.

        Producing no more than ``max_length`` bytes bounds the memory a small
        compressed message can take. `bounded_decompress` does it with a
        decompressor of the standard library.

        Raises:
            ValueError: ``data`` is malformed or cut short.
        """
        ...


def get_compressor(name: str, url: URL) -> Compressor:
    """Return a compressor of the encoding ``name``, such as ``gzip``, created with ``url``.

    Raises:
        ExtensionError: No compressor is installed under ``name``.
    """
    return extensions.get(Compressor, name)(url)


class _Decompressor(typing.Protocol):
    @property
    def eof(self) -> bool: ...

    def decompress(self, data: bytes, max_length: int = -1, /) -> bytes: ...


def bounded_decompress(decompressor: _Decompressor, data: bytes, max_length: int) -> bytes:
    """Return ``data`` decompressed by ``decompressor``, such as ``zlib.decompressobj()``, as `Compressor.decompress` does.

    Raises:
        ValueError: ``data`` is malformed or cut short.
    """
    try:
        result = decompressor.decompress(data, max_length)
    except (zlib.error, OSError) as error:
        raise ValueError(f"malformed compressed data: {error}") from None

    if len(result) < max_length and not decompressor.eof:
        raise ValueError("compressed data is cut short")
    return result
