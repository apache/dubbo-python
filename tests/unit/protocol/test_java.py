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
import datetime
import decimal
import typing
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

import hessian2
import pytest

from dubbo import Method, Parameter
from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.protocol.java import caller_error, java_exception, java_type_name, method_descriptor
from dubbo.rpc.definition import JavaType
from dubbo.serialization import Codec, Reader
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL


@hessian2.java_class("com.example.User")
@dataclasses.dataclass
class User:
    name: str


@dataclasses.dataclass
class Undeclared:
    name: str


@hessian2.java_class("com.example.Cat")
@dataclasses.dataclass
class Cat:
    name: str


class _Unnamed:
    """A format of Java objects that declares no types of its own."""

    content_subtype = "unnamed"

    def __init__(self) -> None:
        self.url = URL(protocol="dubbo")

    def codec(self, types: Any) -> Codec[tuple[Any, ...]]:
        raise NotImplementedError

    def reader(self, data: bytes) -> Reader:
        raise NotImplementedError

    def java_type(self, annotation: Any) -> str | None:
        return None


HESSIAN2 = Hessian2Serialization(URL(protocol="dubbo"))


def _method(*types: Any) -> Method:
    return Method(
        name="find", request=tuple(Parameter(name=f"p{i}", type=t) for i, t in enumerate(types)), response=str
    )


@hessian2.java_class("java.lang.IllegalStateException")
@dataclasses.dataclass
class IllegalState(Exception):
    detail_message: str = ""


@pytest.mark.parametrize(
    ("annotation", "descriptor"),
    [
        (bool, "Z"),
        (int, "I"),
        (float, "D"),
        (hessian2.Long, "J"),
        (bool | None, "Ljava/lang/Boolean;"),
        (int | None, "Ljava/lang/Integer;"),
        (float | None, "Ljava/lang/Double;"),
        (hessian2.Long | None, "Ljava/lang/Long;"),
        (Annotated[int, "other metadata"], "I"),
        (Annotated[hessian2.Long, "the id"], "J"),
        (str, "Ljava/lang/String;"),
        (str | None, "Ljava/lang/String;"),
        (bytes, "[B"),
        (decimal.Decimal, "Ljava/math/BigDecimal;"),
        (datetime.date, "Ljava/time/LocalDate;"),
        (hessian2.BigInteger, "Ljava/math/BigInteger;"),
        (hessian2.Instant, "Ljava/time/Instant;"),
        (hessian2.Date, "Ljava/util/Date;"),
        (hessian2.LocalDateTime, "Ljava/time/LocalDateTime;"),
        (User, "Lcom/example/User;"),
        (User | None, "Lcom/example/User;"),
        (list[User], "Ljava/util/List;"),
        (Sequence[str], "Ljava/util/List;"),
        (list, "Ljava/util/List;"),
        (set[int], "Ljava/util/Set;"),
        (dict[str, User], "Ljava/util/Map;"),
        (Mapping[str, int], "Ljava/util/Map;"),
        (tuple[str, ...], "[Ljava/lang/String;"),
        (tuple[int, ...], "[I"),
        (tuple[int | None, ...], "[Ljava/lang/Integer;"),
        (tuple[User, ...], "[Lcom/example/User;"),
        (tuple[tuple[int, ...], ...], "[[I"),
        (Any, "Ljava/lang/Object;"),
    ],
    ids=repr,
)
def test_a_parameter_type_has_the_java_descriptor(annotation: Any, descriptor: str) -> None:
    assert method_descriptor(HESSIAN2, _method(annotation)) == descriptor


def test_a_method_descriptor_joins_its_parameters() -> None:
    assert method_descriptor(HESSIAN2, _method(str, hessian2.Long, User)) == "Ljava/lang/String;JLcom/example/User;"
    assert method_descriptor(HESSIAN2, _method()) == ""


@pytest.mark.parametrize(
    ("annotation", "name"),
    [(hessian2.Long, "long"), (int | None, "java.lang.Integer"), (tuple[str, ...], "[Ljava.lang.String;")],
    ids=repr,
)
def test_a_java_type_is_named_as_class_get_name_names_it(annotation: Any, name: str) -> None:
    assert java_type_name(HESSIAN2, annotation) == name


@pytest.mark.parametrize(
    ("annotation", "name"),
    [(Annotated[Any, JavaType("long")], "long"), (Annotated[hessian2.Long, JavaType("int")], "int")],
    ids=["any", "long"],
)
def test_a_java_type_in_the_metadata_names_the_type(annotation: Any, name: str) -> None:
    assert java_type_name(HESSIAN2, annotation) == name


def test_a_java_type_in_the_metadata_gives_the_parameter_descriptor() -> None:
    assert method_descriptor(
        HESSIAN2, _method(Annotated[Any, JavaType("[Ljava.lang.String;")], Annotated[Any, JavaType("com.example.User")])
    ) == ("[Ljava/lang/String;Lcom/example/User;")


def test_python_types_have_java_types_whatever_the_serialization() -> None:
    serialization: Any = _Unnamed()

    assert (
        method_descriptor(serialization, _method(int, str, list[str], bytes)) == "ILjava/lang/String;Ljava/util/List;[B"
    )
    with pytest.raises(TypeError, match="has no Java type"):
        method_descriptor(serialization, _method(User))


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (Undeclared, "Undeclared"),
        (User | Cat, "several Java types"),
        (datetime.datetime, "datetime"),
        (tuple[str, int], "tuple\\[X, ...\\]"),
    ],
)
def test_a_type_without_one_java_type_has_no_descriptor(annotation: Any, message: str) -> None:
    with pytest.raises(TypeError, match=f"find has a parameter with no Java type: .*{message}"):
        method_descriptor(HESSIAN2, _method(annotation))


@pytest.mark.skipif(not hasattr(typing, "TypeAliasType"), reason="type aliases arrive in Python 3.12")
def test_an_alias_stands_for_its_type() -> None:
    alias = typing.TypeAliasType("UserId", hessian2.Long)  # type: ignore[attr-defined]

    assert method_descriptor(HESSIAN2, _method(alias, list[alias])) == "JLjava/util/List;"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (Status.DEADLINE_EXCEEDED, 2),
        (Status.PERMISSION_DENIED, 4),
        (Status.UNAVAILABLE, 1),
        (Status.UNIMPLEMENTED, 11),
        (Status.NOT_FOUND, 0),
    ],
)
def test_an_rpc_error_travels_as_an_rpc_exception_with_the_code_java_gives_its_status(
    status: Status, code: int
) -> None:
    sent = java_exception(HESSIAN2, RpcError(status, "why"))

    assert isinstance(sent, RemoteError)
    assert (sent.class_name, sent.message, dict(sent.fields)) == (
        "org.apache.dubbo.rpc.RpcException",
        "why",
        {"code": code},
    )


@pytest.mark.parametrize(
    "error", [RemoteError("com.example.UserNotFound", "bob"), IllegalState("no")], ids=["remote-error", "declared"]
)
def test_an_exception_of_a_java_class_travels_as_itself(error: Exception) -> None:
    assert java_exception(HESSIAN2, error) is error


def test_an_undeclared_python_exception_travels_as_a_runtime_exception() -> None:
    sent = java_exception(HESSIAN2, ValueError("broken"))

    assert isinstance(sent, RemoteError)
    assert (sent.class_name, sent.message) == ("java.lang.RuntimeException", "ValueError: broken")


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (2, Status.DEADLINE_EXCEEDED),
        (8, Status.DEADLINE_EXCEEDED),
        (13, Status.UNAUTHENTICATED),
        (7, Status.UNAVAILABLE),
        (3, Status.UNKNOWN),
        ("x", Status.UNKNOWN),
    ],
    ids=repr,
)
def test_a_received_rpc_exception_takes_the_status_of_its_code(code: object, status: Status) -> None:
    received = caller_error(RemoteError("org.apache.dubbo.rpc.RpcException", "why", fields={"code": code}))

    assert (received.status, received.message) == (status, "why")


def test_a_received_exception_that_is_not_an_rpc_exception_keeps_its_status():
    error = RemoteError("java.lang.IllegalStateException", "x")

    assert caller_error(error) is error
    assert error.status is Status.UNKNOWN
