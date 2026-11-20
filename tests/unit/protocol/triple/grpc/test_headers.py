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

import pytest

from dubbo.protocol.triple.grpc.headers import content_subtype, decode_timeout, encode_timeout


@pytest.mark.parametrize(
    ("seconds", "encoded"),
    [
        (0.05, b"50000000n"),
        (0.5, b"500000u"),
        (1.5, b"1500000u"),
        (1000.0, b"1000000m"),
        (1e6, b"1000000S"),
        (1e9, b"16666667M"),
    ],
)
def test_encode_timeout_uses_the_finest_unit_that_fits_eight_digits(seconds: float, encoded: bytes) -> None:
    assert encode_timeout(seconds) == encoded


@pytest.mark.parametrize(
    ("value", "seconds"), [(b"1H", 3600), (b"2M", 120), (b"3S", 3), (b"4m", 4e-3), (b"5u", 5e-6), (b"6n", 6e-9)]
)
def test_decode_timeout_reads_every_unit(value: bytes, seconds: float) -> None:
    assert decode_timeout(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", [b"", b"1", b"S", b"123456789S", b"-1S", b"1s", b"1.5S"])
def test_decode_timeout_rejects_malformed_values(value: bytes) -> None:
    with pytest.raises(ValueError, match="malformed grpc-timeout"):
        decode_timeout(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (b"application/grpc", b""),
        (b"application/grpc+proto", b"proto"),
        (b"application/grpc+json; charset=utf-8", b"json"),
        (b"application/grpc;x=y", b""),
        (b"application/grpcx", None),
        (b"application/json", None),
        (None, None),
    ],
    ids=["grpc", "protobuf", "json-with-parameters", "grpc-with-parameters", "wrong-suffix", "http-json", "absent"],
)
def test_content_subtype_recognises_only_grpc_media_types(value, expected):
    assert content_subtype(value) == expected
