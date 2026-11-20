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

import dataclasses
from typing import Any

import hessian2
import pytest

from dubbo import Method, Parameter
from dubbo.exceptions import RemoteError, Status
from dubbo.protocol.dubbo.body import (
    MethodCodec,
    ResponseCodec,
    ResponseStatus,
    read_request_head,
    service_version,
    status_error,
    supports_response_attachments,
    to_attachments,
)
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL


@hessian2.java_class("com.example.User")
@dataclasses.dataclass
class User:
    name: str
    age: int


FIND = Method(
    name="find", request=(Parameter(name="name", type=str), Parameter(name="id", type=hessian2.Long)), response=User
)
FORGET = Method(name="forget", request=(Parameter(name="name", type=str),), response=None)
TAGS = Method(name="tags", request=(Parameter(name="tags", type=tuple[str, ...]),), response=set[str])

SERIALIZATION = Hessian2Serialization(URL(protocol="dubbo"))
RESPONSES = ResponseCodec(SERIALIZATION)


def _codec(method: Method = FIND, version: str = "1.0") -> MethodCodec:
    return MethodCodec(RESPONSES, "com.example.UserService", version, method)


def _encode(*values: Any) -> bytes:
    return SERIALIZATION.codec((Any,) * len(values)).encode(values)


def test_a_request_carries_the_call_and_its_attachments() -> None:
    codec = _codec()
    data = codec.encode_request(("bob", 7), {"group": "a"})
    assert hessian2.loads_many(data) == [
        "2.0.2",
        "com.example.UserService",
        "1.0",
        "find",
        "Ljava/lang/String;J",
        "bob",
        7,
        {"group": "a"},
    ]
    reader = SERIALIZATION.reader(data)

    head = read_request_head(reader)

    assert (head.dubbo_version, head.path, head.version) == ("2.0.2", "com.example.UserService", "1.0")
    assert (head.method, head.descriptor) == ("find", "Ljava/lang/String;J")
    assert codec.read_arguments(reader) == (("bob", 7), {"group": "a"})


def test_arguments_decode_as_the_parameter_types() -> None:
    codec = _codec(TAGS)
    reader = SERIALIZATION.reader(codec.encode_request((("a", "b"),), {}))
    read_request_head(reader)

    assert codec.read_arguments(reader) == ((("a", "b"),), {})


def test_an_argument_of_another_type_is_rejected() -> None:
    reader = SERIALIZATION.reader(
        _encode("2.0.2", "com.example.UserService", "1.0", "find", "Ljava/lang/String;J", 1, 7, {})
    )
    read_request_head(reader)

    with pytest.raises(ValueError, match="expected str"):
        _codec().read_arguments(reader)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((), "message ends before this value"),
        (("2.0.2", "a", "1.0", "m"), "message ends before this value"),
        ((1, "a", "", "m", ""), "expected str, got int"),
        (("2.0.2", "a", "1.0", "m", ["not text"]), "expected str, got a list"),
    ],
    ids=["empty", "missing-descriptor", "non-text-version", "non-text-descriptor"],
)
def test_request_heads_reject_missing_or_non_text_fields(values, message):
    with pytest.raises(ValueError, match=message):
        read_request_head(SERIALIZATION.reader(_encode(*values)))


def test_attachments_that_are_no_map_of_text_are_rejected() -> None:
    reader = SERIALIZATION.reader(
        _encode("2.0.2", "a.B", "", "find", "Ljava/lang/String;J", "bob", 7, "not attachments")
    )
    read_request_head(reader)

    with pytest.raises(ValueError, match="expected dict"):
        _codec().read_arguments(reader)


@pytest.mark.parametrize("attachments", [None, {"dubbo": "2.0.2"}])
def test_a_response_carries_the_value(attachments: dict[str, str] | None) -> None:
    codec = _codec()

    response = codec.decode_response(codec.encode_value(User("bob", 3), attachments))

    assert (response.value, response.exception, response.attachments) == (User("bob", 3), None, attachments or {})


def test_a_value_decodes_as_the_return_type() -> None:
    codec = _codec(TAGS)

    assert codec.decode_response(codec.encode_value({"a"}, None)).value == {"a"}


FIND_OR_NONE = Method(name="find", request=FIND.request, response=User | None)


@pytest.mark.parametrize("method", [FIND_OR_NONE, FORGET])
def test_nothing_returned_travels_as_a_null_response(method: Method) -> None:
    codec = _codec(method)

    for attachments in (None, {"k": "v"}):
        response = codec.decode_response(codec.encode_value(None, attachments))
        assert (response.value, response.exception, response.attachments) == (None, None, attachments or {})


@pytest.mark.parametrize("attachments", [None, {"k": "v"}])
def test_a_null_response_fails_a_method_whose_return_type_allows_no_none(attachments: dict[str, str] | None) -> None:
    codec = _codec()

    with pytest.raises(ValueError, match=r"declare User \| None"):
        codec.decode_response(RESPONSES.encode_null(attachments))


@pytest.mark.parametrize("attachments", [None, {"k": "v"}])
def test_a_response_carries_the_exception(attachments: dict[str, str] | None) -> None:
    error = RemoteError("java.lang.IllegalStateException", "bad")

    response = RESPONSES.decode_response(RESPONSES.encode_exception(error, attachments))

    assert isinstance(response.exception, RemoteError)
    assert str(response.exception) == "java.lang.IllegalStateException: bad"
    assert response.attachments == (attachments or {})


def test_values_after_a_response_are_left_unread() -> None:
    codec = _codec()
    data = codec.encode_value(User("bob", 3), None) + SERIALIZATION.codec((None,)).encode((None,))

    assert codec.decode_response(data).value == User("bob", 3)
    assert RESPONSES.decode_message(RESPONSES.encode_message("why") + b"N") == "why"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((), "message ends before this value"),
        (("x",), "expected int, got str"),
        ((9, "v"), "kind is 0 to 5"),
        ((1,), "message ends before this value"),
        ((1, 2), "expected str, got int"),
        ((4, "v"), "message ends before this value"),
        ((4, "v", "not attachments"), "expected dict, got str"),
    ],
    ids=[
        "empty",
        "non-integer-kind",
        "unknown-kind",
        "missing-value",
        "wrong-value-type",
        "missing-attachments",
        "non-map-attachments",
    ],
)
def test_response_bodies_reject_missing_fields_unknown_kinds_and_wrong_types(values, message):
    with pytest.raises(ValueError, match=message):
        RESPONSES.decode_response(_encode(*values), str)


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("2.0.2", True),
        ("2.0.99", True),
        ("2.0.10", True),
        ("2.0.1", False),
        ("2.1.0", False),
        ("3.0.0", False),
        ("", False),
        ("x", False),
    ],
)
def test_response_attachments_reach_consumers_of_2_0_2_to_2_0_99(version: str, supported: bool) -> None:
    assert supports_response_attachments(version) is supported


@pytest.mark.parametrize(
    ("status", "rpc_status"),
    [
        (ResponseStatus.SERVER_TIMEOUT, Status.DEADLINE_EXCEEDED),
        (ResponseStatus.SERVICE_NOT_FOUND, Status.UNAVAILABLE),
        (ResponseStatus.BAD_REQUEST, Status.INVALID_ARGUMENT),
        (ResponseStatus.SERVICE_ERROR, Status.INTERNAL),
        (ResponseStatus.SERVER_ERROR, Status.UNKNOWN),
        (ResponseStatus.CHANNEL_INACTIVE, Status.UNAVAILABLE),
        (99, Status.UNKNOWN),
    ],
)
def test_a_status_reaches_the_consumer_as_an_error(status: int, rpc_status: Status) -> None:
    error = status_error(status, "why")

    assert error.status is rpc_status
    assert error.message.endswith(": why")


def test_received_attachments_become_text() -> None:
    attachments = to_attachments({"a": "x", "b": b"y", "c": 3, "d": True, "e": object()})

    assert dict(attachments) == {"a": "x", "b": b"y", "c": "3", "d": "true"}


@pytest.mark.parametrize("version", ["", "0.0.0", "*", None])
def test_no_version_reads_as_empty(version: str | None) -> None:
    head = read_request_head(SERIALIZATION.reader(_encode("2.0.2", "a.B", version, "m", "")))

    assert head.version == service_version(version) == ""


def test_a_service_without_a_version_is_called_as_0_0_0() -> None:
    reader = SERIALIZATION.reader(_codec(version="").encode_request(("bob", 7), {}))

    assert [reader.load(str) for _ in range(3)][2] == "0.0.0"
