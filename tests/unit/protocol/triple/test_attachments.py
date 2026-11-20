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

import json

import pytest
from multidict import MultiDict

from dubbo.protocol.triple.attachments import attachment_headers, split_headers
from dubbo.protocol.triple.headers import percent_decode, percent_encode


@pytest.mark.parametrize(
    ("attachments", "message"),
    [
        ({"a b": "x"}, "cannot be a gRPC metadata name"),
        ({"grpc-status": "0"}, "cannot be a gRPC metadata name"),
        ({"tri-service-group": "g"}, "cannot be a gRPC metadata name"),
        ({"a": "失"}, "printable ASCII"),
        ({"a": "x\n"}, "printable ASCII"),
        ({"a": b"x"}, "printable ASCII"),
        ({"a-bin": "x"}, "must be bytes"),
        ({"A": "1", "a": "2"}, "differ only in case"),
    ],
)
def test_attachment_headers_reject_what_metadata_cannot_carry(
    attachments: dict[str, str | bytes], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        attachment_headers(attachments)


def test_split_headers_keeps_reserved_fields_out_of_attachments() -> None:
    fields, attachments = split_headers(
        (
            (b":path", b"/s/m"),
            (b"content-type", b"application/grpc"),
            (b"te", b"trailers"),
            (b"grpc-timeout", b"1S"),
            (b"tri-service-version", b"1.0"),
            (b"tri-header-convert", b"not json"),
            (b"user-id", b"\xe5\xa4\xb1"),
            (b"blob-bin", b"AAEC"),
            (b"broken-bin", b"!!!!"),
        )
    )

    assert set(fields) == {
        b":path",
        b"content-type",
        b"te",
        b"grpc-timeout",
        b"tri-service-version",
        b"tri-header-convert",
    }
    assert attachments == {"user-id": "失", "blob-bin": b"\x00\x01\x02"}


@pytest.mark.parametrize(
    ("value", "data"),
    [
        (b"AAEC", [b"\x00\x01\x02"]),
        (b"AAE=", [b"\x00\x01"]),
        (b"AAE", [b"\x00\x01"]),
        (b"AAE, !, AAEC", [b"\x00\x01", b"\x00\x01\x02"]),
    ],
)
def test_binary_attachments_accept_padded_unpadded_and_joined_values(value: bytes, data: list[bytes]) -> None:
    assert split_headers(((b"blob-bin", value),))[1].getall("blob-bin") == data


def test_repeated_attachments_keep_every_value_and_travel_one_field_each() -> None:
    attachments = MultiDict([("Tag", "a"), ("Tag", "b"), ("blob-bin", b"\x01"), ("blob-bin", b"\x02")])

    headers = attachment_headers(attachments)

    assert headers[:4] == [(b"tag", b"a"), (b"tag", b"b"), (b"blob-bin", b"AQ"), (b"blob-bin", b"Ag")]
    received = split_headers(tuple(headers))[1]
    assert received.getall("Tag") == ["a", "b"]
    assert received.getall("blob-bin") == [b"\x01", b"\x02"]


def test_binary_attachments_travel_as_unpadded_base64_under_their_own_key() -> None:
    headers = attachment_headers({"Blob-bin": b"\x00\x01"})

    assert headers[0] == (b"blob-bin", b"AAE")
    assert split_headers(tuple(headers))[1] == {"Blob-bin": b"\x00\x01"}


def test_attachments_travel_as_lowercase_headers_with_their_case_recorded() -> None:
    headers = attachment_headers({"tenant": "a", "Trace-Id": "b"})

    assert headers[:2] == [(b"tenant", b"a"), (b"trace-id", b"b")]
    assert headers[2][0] == b"tri-header-convert"
    assert json.loads(percent_decode(headers[2][1])) == {"trace-id": "Trace-Id"}
    assert split_headers((*headers, (b"grpc-status", b"0"), (b":status", b"200")))[1] == {
        "tenant": "a",
        "Trace-Id": "b",
    }


def test_the_conversion_table_names_each_header_as_sent_with_its_suffix() -> None:
    headers = attachment_headers({"Trace": "a", "trace-bin": b"\x00"})

    assert json.loads(percent_decode(headers[2][1])) == {"trace": "Trace"}
    assert split_headers(tuple(headers))[1] == {"Trace": "a", "trace-bin": b"\x00"}


def test_a_table_entry_without_the_suffix_leaves_a_binary_attachment_as_sent() -> None:
    table = percent_encode('{"trace":"Trace"}')

    _, attachments = split_headers(((b"trace-bin", b"AAH/"), (b"tri-header-convert", table)))

    assert attachments == {"trace-bin": b"\x00\x01\xff"}
