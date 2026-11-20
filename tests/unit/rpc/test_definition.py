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
from collections.abc import Awaitable

import pytest

import dubbo
from dubbo import Method, Parameter, RpcType, Service, get_definition


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("async def m(self, a) -> None: ...", "annotate the type of parameter 'a'"),
        ("async def m(self, a: int): ...", "annotate its return type"),
        ("async def m(self, a: int, /) -> None: ...", "positional-only parameter 'a'"),
        ("async def m(self, *, a: int) -> None: ...", "keyword-only parameter 'a'"),
        ("async def m(self, *a: int) -> None: ...", "variadic positional parameter 'a'"),
        ("async def m(self, **a: int) -> None: ...", "variadic keyword parameter 'a'"),
        ("async def m() -> None: ...", "must take self"),
        ("def m(self) -> None: ...", "must be an async def, or a def returning dubbo.ServerStream"),
        ("async def m(self) -> dubbo.ServerStream[int]: ...", "must be a def, not an async def"),
        ("def m(self) -> dubbo.ServerStream[int]: ...", "exactly one request parameter"),
        ("def m(self, a: int) -> dubbo.BidiStream[int, int]: ...", "requests are sent on the stream"),
        ("m: int", "must be a method"),
        ("async def m(self, s: dubbo.SendStream[int]) -> None: ...", "exactly one request parameter before"),
        ("async def m(self, s: dubbo.SendStream[int], a: int) -> None: ...", "one stream, as its last parameter"),
        ("async def m(self, a: int, s: dubbo.SendStream[int]) -> int: ...", "must return None"),
        ("async def m(self, a: int, s: dubbo.ReceiveStream[int]) -> int: ...", "must take only its stream"),
        ("async def m(self, s: dubbo.Stream) -> None: ...", "message types of its stream 's'"),
        ("def m(self, a: int) -> dubbo.ServerStream: ...", "message types of the stream it returns"),
    ],
    ids=[
        "unannotated",
        "no-return",
        "positional-only",
        "keyword-only",
        "args",
        "kwargs",
        "no-self",
        "sync",
        "async-stream",
        "stream-without-request",
        "bidi-with-parameter",
        "attribute",
        "served-stream-without-request",
        "stream-not-last",
        "served-stream-returns",
        "client-stream-with-request",
        "bare-stream",
        "bare-called-stream",
    ],
)
def test_service_rejects_invalid_members(source: str, message: str) -> None:
    namespace: dict[str, object] = {}
    exec(f"class Contract(typing.Protocol):\n    {source}", {"dubbo": dubbo, "typing": typing}, namespace)

    contract = dubbo.service("Contract")(namespace["Contract"])  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=message):
        dubbo.get_definition(contract)


def test_a_contract_declares_streams_for_one_side() -> None:
    @dubbo.service("Contract")
    class Contract(typing.Protocol):
        def watch(self, query: str) -> dubbo.ServerStream[int]: ...
        async def upload(self, chunks: dubbo.ReceiveStream[bytes]) -> int: ...

    with pytest.raises(TypeError, match="declare each side in its own class"):
        get_definition(Contract)


def test_service_definition_preserves_wire_names_parameter_defaults_and_stream_shapes(contract):
    assert get_definition(contract) == Service(
        interface="com.example.UserService",
        methods=(
            Method(
                name="rename", request=(Parameter(name="id", type=int), Parameter(name="name", type=str)), response=str
            ),
            Method(
                name="findByName",
                request=(Parameter(name="name", type=str), Parameter(name="limit", type=int, default=10)),
                response=list[str],
            ),
            Method(name="fail", request=(Parameter(name="error", type=str),), response=None),
            Method(name="sleep", request=(), response=None),
            Method(
                name="watch", rpc_type=RpcType.SERVER_STREAM, request=(Parameter(name="query", type=str),), response=int
            ),
            Method(
                name="upload",
                rpc_type=RpcType.CLIENT_STREAM,
                request=(Parameter(name="message", type=bytes),),
                response=int,
            ),
            Method(
                name="chat", rpc_type=RpcType.BIDI_STREAM, request=(Parameter(name="message", type=str),), response=str
            ),
        ),
    )


def test_caller_and_servicer_contracts_describe_the_same_service(contract, servicer):
    assert get_definition(servicer) == get_definition(contract)


def test_streaming_methods_need_one_request_parameter():
    with pytest.raises(ValueError, match="server_stream method 'm' must have exactly one request parameter, not 0"):
        Method(name="m", rpc_type=RpcType.SERVER_STREAM, request=(), response=int)


def test_service_definitions_reject_duplicate_method_names():
    method = Method(name="m", request=(), response=None)

    with pytest.raises(ValueError, match="S defines methods more than once: m"):
        Service(interface="S", methods=(method, method))


def test_contract_annotations_resolve_names_defined_later_and_reuse_the_built_definition():
    namespace = {"dubbo": dubbo, "typing": typing}
    exec(
        """
from __future__ import annotations

@dubbo.service("Contract")
class Contract(typing.Protocol):
    async def clone(self) -> Contract: ...
    async def find(self, query: Query) -> Query: ...

class Query: ...
""",
        namespace,
    )

    definition = get_definition(namespace["Contract"])

    assert definition == Service(
        interface="Contract",
        methods=(
            Method(name="clone", request=(), response=namespace["Contract"]),
            Method(
                name="find", request=(Parameter(name="query", type=namespace["Query"]),), response=namespace["Query"]
            ),
        ),
    )
    assert get_definition(namespace["Contract"]) is definition


def test_contract_annotations_resolve_names_inside_annotations_and_keep_defaults():
    namespace = {"dubbo": dubbo, "typing": typing}
    exec(
        """
@dubbo.service("Contract")
class Contract(typing.Protocol):
    def watch(self, query: "Query" = None) -> dubbo.ServerStream["Query"]: ...

class Query: ...
""",
        namespace,
    )

    assert get_definition(namespace["Contract"]).method("watch") == Method(
        name="watch",
        rpc_type=RpcType.SERVER_STREAM,
        request=(Parameter(name="query", type=namespace["Query"], default=None),),
        response=namespace["Query"],
    )


def test_a_contract_has_the_methods_of_the_classes_it_extends():
    @dubbo.service("Parent")
    class Parent(typing.Protocol):
        async def inherited(self) -> int: ...

    @dubbo.service("Child")
    class Child(Parent, typing.Protocol):
        async def own(self) -> int: ...

    class Incomplete(Child):
        async def own(self) -> int:
            return 0

    assert [method.name for method in get_definition(Child).methods] == ["inherited", "own"]
    with pytest.raises(TypeError, match=r"Incomplete\.inherited is not implemented"):
        Service.from_implementation(Incomplete())


def test_unresolvable_annotations_name_the_method():
    namespace = {"dubbo": dubbo, "typing": typing}
    exec(
        """
from __future__ import annotations

@dubbo.service("Contract")
class Contract(typing.Protocol):
    async def broken(self) -> Missing: ...
""",
        namespace,
    )

    with pytest.raises(TypeError, match=r"Contract\.broken has an annotation that cannot be resolved"):
        get_definition(namespace["Contract"])

    namespace["Missing"] = str

    assert get_definition(namespace["Contract"]).method("broken").response is str


def test_contracts_reject_duplicate_wire_names():
    @dubbo.service("Contract")
    class Contract(typing.Protocol):
        @dubbo.method("getUser")
        async def get_user(self) -> None: ...
        @dubbo.method("getUser")
        def watch_user(self, id: int) -> dubbo.ServerStream[int]: ...

    with pytest.raises(ValueError, match="more than once: getUser"):
        get_definition(Contract)


def test_wire_method_names_cannot_be_empty():
    with pytest.raises(ValueError, match="method name must not be empty"):
        dubbo.method("")


@pytest.mark.parametrize(
    ("declaration", "implementation", "message"),
    [
        ("async def find(self) -> None: ...", "pass", r"Implementation\.find is not implemented"),
        (
            "def watch(self, query: str) -> dubbo.ServerStream[int]: ...",
            "pass",
            "declares how callers hold its streaming methods",
        ),
        (
            "async def watch(self, query: str, events: dubbo.SendStream[int]) -> None: ...",
            "async def watch(self, chunks: dubbo.ReceiveStream[str]) -> int: return 0",
            "does not take the arguments of a server_stream method",
        ),
        (
            "async def upload(self, chunks: dubbo.ReceiveStream[bytes]) -> int: ...",
            "def upload(self, chunks: dubbo.ReceiveStream[bytes]) -> Awaitable[int]: ...",
            r"Implementation\.upload must be an async def",
        ),
        (
            "async def find(self, name: str, limit: int = 10) -> list[str]: ...",
            "async def find(self, name: str) -> list[str]: return []",
            "does not take the arguments of a unary method",
        ),
    ],
    ids=["missing-handler", "caller-view", "wrong-stream-shape", "synchronous-handler", "wrong-unary-arity"],
)
def test_implementations_supply_async_handlers_with_the_contract_arguments(declaration, implementation, message):
    namespace = {"dubbo": dubbo, "typing": typing, "Awaitable": Awaitable}
    exec(
        f"@dubbo.service('Contract')\nclass Contract(typing.Protocol):\n    {declaration}\n\nclass Implementation(Contract):\n    {implementation}",
        namespace,
    )

    with pytest.raises(TypeError, match=message):
        Service.from_implementation(namespace["Implementation"]())


def test_implementations_need_a_service_contract():
    with pytest.raises(TypeError, match="object does not implement a service contract"):
        Service.from_implementation(object())
