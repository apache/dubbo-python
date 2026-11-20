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

import datetime
import enum
import typing
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

import attrs
import hessian2
import pytest

from dubbo import Method, Parameter
from dubbo.exceptions import Status
from dubbo.protocol.generic import GENERIC_INVOKE, GenericInvoker
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invocation, Result
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL

pytestmark = pytest.mark.anyio


@hessian2.java_class("com.example.Color")
class Color(enum.Enum):
    RED = "r"


@hessian2.java_class("com.example.Paint")
@attrs.define(kw_only=True)
class Paint:
    main_color: Color | None
    shades: tuple[Color, ...]
    by_name: dict[str, Color]


_PAINT = Method(
    name="paint",
    request=(Parameter(name="color", type=Color), Parameter(name="paint", type=Paint)),
    response=str,
)


@hessian2.java_class("com.example.Shade")
@attrs.define(kw_only=True)
class Shade:
    _main_color: Color


@hessian2.java_class("com.example.Pair")
@attrs.define(kw_only=True)
class Pair:
    values: tuple[int, int]


async def _call(*arguments: Any, method: Method = _PAINT) -> tuple[Result, list[Invocation]]:
    called: list[Invocation] = []

    async def invoke(invocation: Invocation) -> Result:
        called.append(invocation)
        return Result(value="ok")

    serialization = Hessian2Serialization(URL.parse("tri://127.0.0.1/x?serialization=hessian2"))
    invoker = GenericInvoker(invoke, Service(interface="x", methods=(method,)), serialization)
    invocation = Invocation(
        interface="x", method="$invoke", definition=GENERIC_INVOKE, arguments=(method.name, None, arguments)
    )

    return await invoker.invoke(invocation), called


async def test_enum_names_realize_as_the_enums_the_parameters_declare() -> None:
    paint = {"class": "com.example.Paint", "mainColor": "RED", "shades": ["RED"], "byName": {"a": "RED"}}

    result, called = await _call("RED", paint)

    assert result.error is None
    assert called[0].arguments == (
        Color.RED,
        Paint(main_color=Color.RED, shades=(Color.RED,), by_name={"a": Color.RED}),
    )


async def test_a_name_of_no_member_stands_for_none_of_the_parameters() -> None:
    result, called = await _call("BLUE", None)

    assert (result.error.status, called) == (Status.INVALID_ARGUMENT, [])


_TYPE_ALIAS = getattr(typing, "TypeAliasType", None)


def _method(annotation: Any) -> Method:
    return Method(name="take", request=(Parameter(name="value", type=annotation),), response=str)


@pytest.mark.parametrize(
    ("annotation", "argument", "expected"),
    [
        (Annotated[Color, "documented"], "RED", Color.RED),
        (Mapping[str, Color], {"a": "RED"}, {"a": Color.RED}),
        (Sequence[Color], ["RED"], [Color.RED]),
        pytest.param(
            _TYPE_ALIAS and _TYPE_ALIAS("Colour", Color),
            "RED",
            Color.RED,
            marks=pytest.mark.skipif(_TYPE_ALIAS is None, reason="type statements need Python 3.12"),
        ),
        (Shade, {"class": "com.example.Shade", "_mainColor": "RED"}, Shade(main_color=Color.RED)),
        (datetime.date, "2026-11-15", datetime.date(2026, 11, 15)),
        (datetime.time, "12:34", datetime.time(12, 34)),
        (hessian2.LocalDateTime, "2026-11-15T12:34:56", datetime.datetime(2026, 11, 15, 12, 34, 56)),
    ],
    ids=["annotated", "mapping", "sequence", "type-alias", "leading-underscore", "date", "time", "date-time"],
)
async def test_values_realize_as_the_parameters_declare_them(annotation: Any, argument: Any, expected: Any) -> None:
    result, called = await _call(argument, method=_method(annotation))

    assert result.error is None
    assert called[0].arguments == (expected,)


async def test_a_tuple_of_another_length_stands_for_none_of_the_parameters() -> None:
    result, called = await _call({"class": "com.example.Pair", "values": [1, 2, 3]}, method=_method(Pair))

    assert (result.error.status, called) == (Status.INVALID_ARGUMENT, [])
