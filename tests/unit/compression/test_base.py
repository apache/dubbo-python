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

import bz2
import gzip
import os
import time
import zlib
from collections.abc import Callable

import pytest

from dubbo.compression import Compressor
from dubbo.compression.bzip2 import Bzip2Compressor
from dubbo.compression.deflate import DeflateCompressor
from dubbo.compression.gzip import GzipCompressor
from dubbo.extension import extensions
from dubbo.url import URL

_URL = URL(protocol="tri")


_ROUND_TRIPS = [
    pytest.param(GzipCompressor, gzip.compress, gzip.decompress, id="gzip"),
    pytest.param(DeflateCompressor, zlib.compress, zlib.decompress, id="deflate"),
    pytest.param(Bzip2Compressor, bz2.compress, bz2.decompress, id="bzip2"),
]


_STANDARD_COMPRESSION = [
    pytest.param(GzipCompressor, gzip.compress, id="gzip"),
    pytest.param(DeflateCompressor, zlib.compress, id="deflate"),
    pytest.param(Bzip2Compressor, bz2.compress, id="bzip2"),
]


def test_compressors_are_named_by_their_encoding() -> None:
    assert extensions.names(Compressor) == ["bzip2", "deflate", "gzip"]
    assert extensions.get(Compressor, "gzip") is GzipCompressor
    assert extensions.get(Compressor, "deflate") is DeflateCompressor
    assert extensions.get(Compressor, "bzip2") is Bzip2Compressor


@pytest.mark.parametrize(("compressor", "compress", "decompress"), _ROUND_TRIPS)
def test_compressors_round_trip_their_standard_format(
    compressor: type[Compressor], compress: Callable[[bytes], bytes], decompress: Callable[[bytes], bytes]
) -> None:
    instance = compressor(_URL)

    assert instance.decompress(compress(b"hello"), 100) == b"hello"
    assert instance.decompress(instance.compress(b"hello"), 100) == b"hello"
    assert decompress(instance.compress(b"hello")) == b"hello"


@pytest.mark.parametrize(("compressor", "compress"), _STANDARD_COMPRESSION)
def test_decompress_stops_at_max_length(compressor: type[Compressor], compress: Callable[[bytes], bytes]) -> None:
    assert compressor(_URL).decompress(compress(b"\0" * 1000), 10) == b"\0" * 10


@pytest.mark.parametrize(("compressor", "compress"), _STANDARD_COMPRESSION)
def test_decompress_rejects_malformed_and_cut_short_data(
    compressor: type[Compressor], compress: Callable[[bytes], bytes]
) -> None:
    instance = compressor(_URL)

    with pytest.raises(ValueError, match="malformed"):
        instance.decompress(b"not compressed", 100)
    with pytest.raises(ValueError, match="cut short"):
        instance.decompress(compress(b"hello")[:-4], 100)


def test_gzip_decompresses_every_member_of_a_message() -> None:
    data = gzip.compress(b"first") + gzip.compress(b"last")

    assert GzipCompressor(_URL).decompress(data, 100) == b"firstlast"


def test_gzip_members_share_the_max_length() -> None:
    data = gzip.compress(b"x" * 6) + gzip.compress(b"y" * 6)

    assert GzipCompressor(_URL).decompress(data, 8) == b"x" * 6 + b"y" * 2


def test_gzip_rejects_a_cut_short_last_member() -> None:
    data = gzip.compress(b"first") + gzip.compress(b"last")[:-4]

    with pytest.raises(ValueError, match="cut short"):
        GzipCompressor(_URL).decompress(data, 100)


def test_gzip_decompresses_members_of_any_length_after_the_first() -> None:
    long = os.urandom(100_000)
    data = gzip.compress(b"first") + gzip.compress(long) + gzip.compress(b"last")

    assert GzipCompressor(_URL).decompress(data, 200_000) == b"first" + long + b"last"
    with pytest.raises(ValueError, match="malformed"):
        GzipCompressor(_URL).decompress(data + b"not compressed", 200_000)


def test_gzip_decompresses_many_members_in_linear_time() -> None:
    data = gzip.compress(b"", mtime=0) * 200_000
    started = time.perf_counter()

    assert GzipCompressor(_URL).decompress(data, 100) == b""
    # Quadratic decompression takes about nine seconds here, linear a tenth of one.
    assert time.perf_counter() - started < 3
