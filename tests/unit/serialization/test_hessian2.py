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
import enum
from typing import Annotated, Any

import attrs
import hessian2
import pytest

from dubbo.exceptions import RemoteError, Status
from dubbo.extension import extensions
from dubbo.serialization import JavaSerialization, Serialization, get_java_serialization
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL


@hessian2.java_class("com.example.Address")
@dataclasses.dataclass
class Address:
    city: str
    postal_code: str


@hessian2.java_class("com.example.User")
@dataclasses.dataclass
class User:
    user_id: hessian2.Long
    tags: list[hessian2.Long]
    address: Address


@hessian2.java_class("java.lang.IllegalStateException")
@dataclasses.dataclass
class IllegalState(Exception):
    detail_message: str = ""


@dataclasses.dataclass
class Undeclared:
    name: str


def _serialization() -> Hessian2Serialization:
    return Hessian2Serialization(URL(protocol="dubbo"))


def _user() -> User:
    return User(user_id=7, tags=[1, 2], address=Address(city="Hangzhou", postal_code="310000"))


def test_hessian2_is_named_hessian2_and_carries_java_objects() -> None:
    assert extensions.get(Serialization, "hessian2") is Hessian2Serialization
    assert isinstance(_serialization(), JavaSerialization)
    assert isinstance(get_java_serialization(URL(protocol="dubbo")), Hessian2Serialization)


def test_a_codec_decodes_the_classes_its_types_name() -> None:
    codec = _serialization().codec((str, User, dict[str, Any]))
    values = ("find", _user(), {"path": "com.example.UserService"})

    assert codec.decode(codec.encode(values)) == values


def test_a_codec_builds_the_containers_its_types_name() -> None:
    codec = _serialization().codec((tuple[str, ...], set[int]))

    assert codec.decode(codec.encode((("a", "b"), {1}))) == (("a", "b"), {1})


def test_a_codec_rejects_types_hessian2_cannot_decode() -> None:
    with pytest.raises(TypeError, match="several members"):
        _serialization().codec((list[int] | set[int],))


def test_a_codec_rejects_a_value_of_another_type() -> None:
    data = _serialization().codec((int,)).encode((1,))

    with pytest.raises(ValueError, match="expected str"):
        _serialization().codec((str,)).decode(data)


def test_a_codec_rejects_another_number_of_values() -> None:
    data = _serialization().codec((str,)).encode(("one",))

    with pytest.raises(ValueError):  # noqa: PT011 - the count is hessian2's to word
        _serialization().codec((str, str)).decode(data)


def test_a_codec_writes_tagged_types() -> None:
    serialization = _serialization()
    tagged = serialization.codec((hessian2.Long,))
    plain = serialization.codec((int,))

    assert tagged.encode((1,)) != plain.encode((1,))
    assert tagged.decode(tagged.encode((1,))) == (1,)


def test_an_object_where_any_value_fits_decodes_as_a_hessian_object() -> None:
    data = _serialization().codec((User,)).encode((_user(),))

    (value,) = _serialization().codec((Any,)).decode(data)

    assert isinstance(value, hessian2.HessianObject)
    assert value.class_name == "com.example.User"


def test_a_value_without_a_java_name_cannot_be_encoded() -> None:
    with pytest.raises(TypeError, match="Undeclared"):
        _serialization().codec((Undeclared,)).encode((Undeclared(name="a"),))


def test_a_reader_reads_values_one_at_a_time() -> None:
    serialization = _serialization()
    data = serialization.codec((str, User, None)).encode(("user", _user(), None))

    reader = serialization.reader(data)

    assert reader.load(str) == "user"
    assert reader.load(User) == _user()
    with pytest.raises(ValueError, match="expected int"):
        serialization.reader(data).load(int)


def test_a_reader_fails_after_the_last_value() -> None:
    reader = _serialization().reader(_serialization().codec((str,)).encode(("only",)))

    reader.load(str)
    with pytest.raises(ValueError, match="ends before this value"):
        reader.load(str)


@pytest.mark.parametrize(
    ("annotation", "name"),
    [
        (hessian2.Long, "long"),
        (Annotated[hessian2.Long, "the id"], "long"),
        (User, "com.example.User"),
        (str, "java.lang.String"),
        (decimal.Decimal, "java.math.BigDecimal"),
        (hessian2.Instant, "java.time.Instant"),
        (IllegalState, "java.lang.IllegalStateException"),
        (int, None),
        (list[str], None),
        (Undeclared, None),
    ],
    ids=repr,
)
def test_java_type_names_what_hessian2_declares(annotation: Any, name: str | None) -> None:
    assert _serialization().java_type(annotation) == name


def test_a_remote_error_travels_as_an_object_of_its_class() -> None:
    codec = _serialization().codec((Exception,))
    error = RemoteError("java.lang.IllegalStateException", "no user", fields={"code": 7})

    data = codec.encode((error,))
    (received,) = codec.decode(data)
    (sent,) = _serialization().codec((Any,)).decode(data)

    assert sent.class_name == "java.lang.IllegalStateException"
    assert sent.fields["detailMessage"] == "no user"
    assert isinstance(received, RemoteError)
    assert (received.status, received.class_name, received.message) == (
        Status.UNKNOWN,
        "java.lang.IllegalStateException",
        "no user",
    )
    assert received.fields["code"] == 7
    assert str(received) == "java.lang.IllegalStateException: no user"


def test_a_forwarded_remote_error_keeps_its_cause() -> None:
    serialization = _serialization()
    cause = hessian2.HessianObject("java.io.IOException", {"detailMessage": "disk"})
    data = serialization.codec((Any,)).encode(
        (hessian2.HessianObject("java.lang.IllegalStateException", {"detailMessage": "no", "cause": cause}),)
    )

    received = serialization.reader(data).load(Exception)
    (forwarded,) = serialization.codec((Any,)).decode(serialization.codec((Exception,)).encode((received,)))

    assert forwarded.fields["cause"] == cause


def test_a_declared_exception_travels_as_its_class() -> None:
    serialization = _serialization()

    data = serialization.codec((Exception,)).encode((IllegalState("broken"),))

    assert str(serialization.reader(data).load(Exception)) == "java.lang.IllegalStateException: broken"


def test_a_throwable_sent_as_text_reads_as_an_exception() -> None:
    data = _serialization().codec((str,)).encode(("java.lang.NullPointerException",))

    error = _serialization().reader(data).load(Exception)

    assert (error.class_name, error.message) == ("java.lang.Exception", "java.lang.NullPointerException")


@hessian2.java_class("com.example.Color")
class _Color(enum.Enum):
    RED = "r"


@hessian2.java_class("com.example.Address")
@attrs.define(kw_only=True)
class _Address:
    city: str


@hessian2.java_class("com.example.User")
@attrs.define(kw_only=True)
class _Member:
    name: str
    user_id: hessian2.Long
    address: _Address | None
    color: _Color | None
    tags: tuple[str, ...]


def test_generalizing_keeps_the_java_types_of_the_fields() -> None:
    serialization = _serialization()
    user = _Member(name="bob", user_id=7, address=None, color=_Color.RED, tags=("a",))

    generalized = serialization.generalize((user,), tuple[_Member, ...])

    codec = hessian2.Codec()
    # A long stays a long and a String[] stays one, as encoding the user writes them; the array of users is
    # an array of objects, now maps.
    assert hessian2.Typed(7, hessian2.Long) in generalized.value[0].values()
    data = codec.dumps(generalized)
    assert b"\xe7" in data
    assert b"[string" in data
    assert b"[object" in data
    assert codec.loads(data) == [
        {"class": "com.example.User", "name": "bob", "userId": 7, "address": None, "color": "RED", "tags": ["a"]}
    ]


def test_generalizing_leaves_a_null_alone() -> None:
    serialization = _serialization()

    assert serialization.generalize(None, _Member | None) is None


def test_generalizing_refuses_what_holds_itself_or_has_no_java_class() -> None:
    serialization = _serialization()
    looped: list[Any] = []
    looped.append(looped)

    with pytest.raises(ValueError, match="holds itself"):
        serialization.generalize(looped, Any)
    with pytest.raises(TypeError):
        serialization.generalize(object(), Any)


@hessian2.java_class("com.example.Tint")
@attrs.define(frozen=True, kw_only=True)
class _Tint:
    color: _Color


def test_generalizing_reaches_an_object_that_several_hold_once() -> None:
    shared: list[Any] = [_Color.RED]
    for _ in range(16):
        shared = [shared, shared]

    generalized = _serialization().generalize(shared, Any)

    # Each level doubles the paths to the innermost list, but not the work: the halves stay one list.
    assert generalized[0] is generalized[1]


@pytest.mark.parametrize(
    ("value", "annotation", "expected"),
    [
        ({_Color.RED}, set[_Color], {"RED"}),
        (frozenset({_Color.RED}), frozenset[_Color], frozenset({"RED"})),
        ({_Tint(color=_Color.RED)}, set[_Tint], [{"class": "com.example.Tint", "color": "RED"}]),
    ],
    ids=["set", "frozenset", "set-of-objects"],
)
def test_generalizing_reaches_into_sets(value: Any, annotation: Any, expected: Any) -> None:
    assert _serialization().generalize(value, annotation) == expected


@pytest.mark.parametrize(
    ("value", "annotation", "expected"),
    [
        (datetime.date(2026, 11, 15), datetime.date, "2026-11-15"),
        (datetime.time(12, 34), datetime.time, "12:34"),
        (datetime.time(12, 34, 56, 789000), datetime.time, "12:34:56.789"),
        (datetime.datetime(2026, 11, 15, 12, 34, 56), hessian2.LocalDateTime, "2026-11-15T12:34:56"),
        (datetime.datetime(2026, 11, 15, 12, 34, 0, 1), hessian2.LocalDateTime, "2026-11-15T12:34:00.000001"),
    ],
    ids=["local-date", "local-time-minutes", "local-time-millis", "local-date-time", "local-date-time-micros"],
)
def test_generalizing_gives_java_time_values_as_java_prints_them(value: Any, annotation: Any, expected: str) -> None:
    assert _serialization().generalize(value, annotation) == expected
