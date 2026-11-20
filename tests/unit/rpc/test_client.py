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

import inspect
import typing
from typing import Annotated, Any

import attrs
import pytest

import dubbo
from dubbo import Invocation, Method, Parameter, Result, RpcError, Status, get_definition
from dubbo.rpc.client import GenericService, proxy
from dubbo.rpc.definition import JavaType

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("args", "kwargs", "arguments"),
    [(("a",), {"limit": 2}, ("a", 2)), ((), {"name": "b"}, ("b", 10)), (("c", 3), {}, ("c", 3))],
    ids=["mixed", "keyword-and-default", "positional"],
)
async def test_proxy_binds_arguments_in_parameter_order(args, kwargs, arguments, contract, recording):
    users = proxy(contract, recording.invoke)

    result = await users.find(*args, **kwargs)

    assert result == "answer"
    assert recording.calls == [
        Invocation(
            interface="com.example.UserService",
            method="findByName",
            definition=get_definition(contract).method("findByName"),
            arguments=arguments,
        )
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [((), "missing a required argument"), (("c", 3, 4), "too many positional arguments")],
    ids=["missing", "too-many"],
)
async def test_proxy_reports_bad_arguments_before_making_the_call(args, message, contract, recording):
    users = proxy(contract, recording.invoke)

    with pytest.raises(TypeError, match=rf"find\(\): {message}"):
        await users.find(*args)

    assert recording.calls == []


@attrs.frozen
class Stock:
    sku: str
    on_hand: int


@dubbo.service("com.example.Inventory")
class Inventory(typing.Protocol):
    @dubbo.method("GetStock")
    async def get_stock(self, sku: "str", warehouse: str = "SH") -> "Stock":
        """Return the stock of a SKU in a warehouse.

        Args:
            sku: Stock keeping unit.
            warehouse: Code of the warehouse.
        """
        ...

    def watch(self, sku: str) -> dubbo.ServerStream["Stock"]:
        """Stream each change of the stock of a SKU."""


def test_proxy_methods_have_the_name_signature_annotations_and_docstring_of_the_contract(recording):
    inventory = proxy(Inventory, recording.invoke)

    for name in ("get_stock", "watch"):
        method = getattr(inventory, name)
        declared = getattr(Inventory, name)
        assert method.__name__ == name
        assert method.__doc__ == declared.__doc__
        assert list(inspect.signature(method).parameters) == list(inspect.signature(declared).parameters)[1:]
        assert typing.get_type_hints(method) == typing.get_type_hints(declared)

    assert typing.get_type_hints(inventory.get_stock) == {"sku": str, "warehouse": str, "return": Stock}
    assert inspect.iscoroutinefunction(inventory.get_stock)
    assert not inspect.iscoroutinefunction(inventory.watch)


def test_proxy_requires_the_caller_view_of_a_streaming_contract(servicer, recording):
    with pytest.raises(TypeError, match="declares how its streaming methods are served"):
        proxy(servicer, recording.invoke)


@pytest.mark.parametrize(
    ("types", "annotations"),
    [
        (None, [Any, Any]),
        (["java.lang.String", "int"], [Annotated[Any, JavaType("java.lang.String")], Annotated[Any, JavaType("int")]]),
    ],
    ids=["inferred-any", "java-types"],
)
async def test_generic_calls_describe_a_unary_method_without_the_service_contract(types, annotations, recording):
    users = GenericService("com.example.UserService", recording.invoke)

    result = await users.call("findByName", "g", 2, types=types)

    assert result == "answer"
    assert recording.calls == [
        Invocation(
            interface="com.example.UserService",
            method="findByName",
            generic="true",
            arguments=("g", 2),
            definition=Method(
                name="findByName",
                request=tuple(
                    Parameter(name=f"arg{index}", type=annotation) for index, annotation in enumerate(annotations)
                ),
                response=Any,
            ),
        )
    ]


@pytest.mark.parametrize(
    "types", [["int"], "java.lang.String", ["java.lang.String", ""]], ids=["wrong-count", "bare-string", "empty-type"]
)
async def test_generic_calls_require_one_nonempty_java_type_per_argument(types, recording):
    with pytest.raises(TypeError, match="one Java type for each of the 2 arguments"):
        await GenericService("com.example.UserService", recording.invoke).call("findByName", "g", 2, types=types)

    assert recording.calls == []


def test_generic_services_refuse_unknown_modes(recording):
    with pytest.raises(ValueError, match=r"generic must be one of .*not 'nativejava'"):
        GenericService("com.example.UserService", recording.invoke, generic="nativejava")


@pytest.mark.parametrize("generic", [False, True], ids=["contract", "generic"])
async def test_unary_calls_raise_the_returned_error_and_record_response_attachments(generic, contract, recording):
    error = RpcError(Status.PERMISSION_DENIED, "operator required")
    recording.result = Result(error=error, attachments={"audit-id": "7"})

    request = (
        GenericService("com.example.UserService", recording.invoke).call("fail", "rpc")
        if generic
        else proxy(contract, recording.invoke).fail("rpc")
    )

    with dubbo.outgoing() as call, pytest.raises(RpcError, match="PERMISSION_DENIED: operator required") as raised:
        await request

    assert raised.value is error
    assert raised.value.__cause__ is None
    assert dict(call.response_attachments) == {"audit-id": "7"}


@attrs.define(kw_only=True)
class _Stream:
    response_attachments: dict[str, str] = attrs.field(factory=lambda: {"query": "3"})
    closed: bool = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True


async def test_a_stream_sends_the_attachments_present_when_its_block_opens(contract, recording):
    stream = _Stream()
    recording.result = Result(value=stream)
    opening = proxy(contract, recording.invoke).watch("1")
    assert recording.calls == []

    with dubbo.outgoing({"operator": "alice"}):
        async with opening as opened:
            assert opened is stream

    assert recording.calls == [
        Invocation(
            interface="com.example.UserService",
            method="watch",
            definition=get_definition(contract).method("watch"),
            arguments=("1",),
            attachments={"operator": "alice"},
        )
    ]
    assert stream.closed is True


async def test_a_stream_records_its_response_attachments_on_exit(contract, recording):
    stream = _Stream()
    recording.result = Result(value=stream)

    with dubbo.outgoing() as call:
        async with proxy(contract, recording.invoke).watch("3"):
            pass

    assert stream.closed is True
    assert dict(call.response_attachments) == {"query": "3"}


async def test_a_stream_leaves_the_callers_exception_unwrapped(contract, recording):
    stream = _Stream()
    recording.result = Result(value=stream)

    with dubbo.outgoing() as call, pytest.raises(KeyError, match="mine"):
        async with proxy(contract, recording.invoke).watch("3"):
            raise KeyError("mine")

    assert stream.closed is True
    assert dict(call.response_attachments) == {"query": "3"}


async def test_a_failed_stream_opening_raises_the_error_and_records_its_attachments(contract, recording):
    error = RpcError(Status.ABORTED, "watch failed")
    recording.result = Result(error=error, attachments={"query": "fail"})

    with dubbo.outgoing() as call, pytest.raises(RpcError, match="ABORTED: watch failed") as raised:
        async with proxy(contract, recording.invoke).watch("fail"):
            pytest.fail("the stream must not open")

    assert raised.value is error
    assert dict(call.response_attachments) == {"query": "fail"}
