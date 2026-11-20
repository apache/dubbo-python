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

import enum
import functools
import inspect
import typing
from collections.abc import Awaitable, Callable, Iterator, Mapping
from types import MappingProxyType, NoneType
from typing import Any, Self, TypeVar, cast, get_args, get_origin

import attrs

from .stream import BidiStream, ClientStream, ReceiveStream, SendStream, ServerStream, Stream

__all__ = [
    "Handler",
    "JavaType",
    "Method",
    "Parameter",
    "RpcType",
    "Service",
    "arity",
    "check_handler",
    "get_contract_methods",
    "get_definition",
    "method",
    "service",
]

C = TypeVar("C", bound=type)
F = TypeVar("F", bound=Callable[..., Any])

# Serves one method: the arguments in parameter order, a streaming method's stream last.
Handler = Callable[..., Awaitable[Any]]

# The class attribute that carries what `service` declares about a contract.
_SERVICE_ATTRIBUTE = "__dubbo_service__"
# The class attribute that keeps the definition built from that declaration, and its methods by attribute.
_DEFINITION_ATTRIBUTE = "__dubbo_definition__"
# The function attribute that carries what `method` declares about a contract method.
_METHOD_ATTRIBUTE = "__dubbo_method__"


class RpcType(enum.Enum):
    """How the requests and responses of a method flow."""

    UNARY = "unary"
    SERVER_STREAM = "server_stream"
    CLIENT_STREAM = "client_stream"
    BIDI_STREAM = "bidi_stream"


# The type a caller's method returns for each kind of streaming call.
_CALL_TYPES: dict[type, RpcType] = {
    ServerStream: RpcType.SERVER_STREAM,
    ClientStream: RpcType.CLIENT_STREAM,
    BidiStream: RpcType.BIDI_STREAM,
}
# The type of the stream an implementation's method takes for each kind of streaming call.
_HANDLER_STREAM_TYPES: dict[type, RpcType] = {
    SendStream: RpcType.SERVER_STREAM,
    ReceiveStream: RpcType.CLIENT_STREAM,
    Stream: RpcType.BIDI_STREAM,
}


class _View(enum.Enum):
    """Which side a contract declares its streaming methods for."""

    CALLER = "caller"
    IMPLEMENTATION = "implementation"


@attrs.define(frozen=True)
class JavaType:
    """Names the Java type a value travels as, in the metadata of an annotation.

    A generic call that names the Java types of its arguments types each as
    ``Annotated[Any, JavaType("long")]``; the protocols that call Java
    methods, such as Dubbo, take the name over what the annotation stands for.

    Attributes:
        name: The Java type, named as ``Class.getName`` names it, such as
            ``long``, ``java.lang.String`` or ``[Ljava.lang.String;``.
    """

    name: str


@attrs.define(frozen=True, kw_only=True)
class Parameter:
    """A parameter of a method.

    Arguments travel in parameter order; formats that name them, such as a
    JSON object, use the parameter names.

    Attributes:
        name: Parameter name.
        type: Type annotation, used to serialize the argument.
        default: Value used when a caller leaves the argument out;
            ``inspect.Parameter.empty`` when the parameter is required.
    """

    name: str
    type: Any
    default: Any = inspect.Parameter.empty


def _request(value: Any) -> tuple[Parameter, ...]:
    return value if isinstance(value, tuple) else (Parameter(name="request", type=value),)


@attrs.define(frozen=True, kw_only=True)
class Method:
    """A method of a service, and on the serving side, its handler.

    Written by hand, as in ``Method(name="SayHello", request=HelloRequest,
    response=HelloReply, handler=say_hello)``, it describes a method without
    a contract class.

    Attributes:
        name: Method name shared with other languages, such as ``"getUser"``.
        request: Parameters of each request; one type stands for one
            parameter. A unary method may have any number; a streaming method
            has exactly one: the request of a server stream, or each message
            of a client or bidirectional stream.
        response: Type annotation of each response; ``None`` when a unary
            method returns nothing.
        rpc_type: Whether the requests and the responses are one message or
            a stream.
        handler: What serves the method: an ``async def`` taking the
            arguments of a unary method; the request, then the stream to
            send the responses on, for a server stream; or the stream for a
            client or bidirectional stream. ``None`` where the method is only
            called.
    """

    name: str
    request: tuple[Parameter, ...] = attrs.field(converter=_request)
    response: Any
    rpc_type: RpcType = RpcType.UNARY
    handler: Handler | None = attrs.field(default=None, eq=False, repr=False)

    def __attrs_post_init__(self) -> None:
        if self.rpc_type is not RpcType.UNARY and len(self.request) != 1:
            raise ValueError(
                f"{self.rpc_type.value} method {self.name!r} must have exactly one request parameter, "
                f"not {len(self.request)}"
            )


@attrs.define(frozen=True, kw_only=True)
class Service:
    """A service: what it looks like on the wire, and on the serving side, the handlers of its methods.

    A contract class declares one, which `get_definition` returns; an
    implementation of it gives one with handlers through `from_implementation`.
    It can also be written by hand and exported as it is.

    Attributes:
        interface: Service name shared with other languages, such as
            ``"com.example.UserService"``.
        methods: Methods of the service, with distinct names.
    """

    interface: str
    methods: tuple[Method, ...] = attrs.field(converter=tuple)
    _by_name: dict[str, Method] = attrs.field(
        init=False,
        eq=False,
        repr=False,
        default=attrs.Factory(lambda self: {method.name: method for method in self.methods}, takes_self=True),
    )

    def __attrs_post_init__(self) -> None:
        if len(self._by_name) == len(self.methods):
            return

        names = [method.name for method in self.methods]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"{self.interface} defines methods more than once: {', '.join(duplicates)}")

    @classmethod
    def from_implementation(cls, implementation: object) -> Self:
        """Return the service ``implementation`` implements, with its handlers.

        Raises:
            TypeError: ``implementation`` does not implement a service
                contract, leaves a method unimplemented, or implements one
                with the wrong kind of handler.
        """
        if get_contract(type(implementation)) is None:
            raise TypeError(f"{type(implementation).__qualname__} does not implement a service contract")

        built = _built(implementation)
        if built.view is _View.CALLER:
            raise TypeError(
                f"{type(implementation).__qualname__} implements {built.contract.__qualname__}, which declares "
                "how callers hold its streaming methods; implement the class that declares how they are "
                "served, such as the generated servicer"
            )

        methods = [
            _implemented(implementation, built.contract, attribute, method)
            for attribute, method in built.methods.items()
        ]

        return cls(interface=built.service.interface, methods=methods)

    def method(self, name: str) -> Method:
        """Return the method called ``name``.

        Raises:
            KeyError: The service has no such method.
        """
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"{self.interface} has no method {name!r}") from None


# Declarations hold what the decorators are given. Definitions are built from
# them on first use, when the module has finished defining the names that
# annotations refer to, including the contract itself.


@attrs.define(frozen=True, kw_only=True)
class _ServiceDeclaration:
    interface: str


@attrs.define(frozen=True, kw_only=True)
class _MethodDeclaration:
    name: str


@attrs.define(frozen=True, kw_only=True)
class _Built:
    """The definition built from a contract, by the attributes that declare its methods."""

    contract: type
    service: Service
    methods: Mapping[str, Method]
    # The side the streaming methods are declared for; None when every method is unary, so it serves both sides.
    view: _View | None


def service(interface: str) -> Callable[[C], C]:
    """Declare a class as the contract of a service called ``interface``.

    Each public method is a method of the service. A unary method is an
    ``async def``, the same for callers and implementations. A streaming
    method is declared for one side, so a service with streaming methods
    has a contract for each. Callers hold a ``def`` returning the call:
    `ServerStream`, `ClientStream` or `BidiStream`::

        @dubbo.service("com.example.UserService")
        class UserService(typing.Protocol):
            async def rename(self, id: int, name: str) -> None: ...
            def watch(self, query: Query) -> dubbo.ServerStream[Event]: ...
            def upload(self) -> dubbo.ClientStream[Chunk, int]: ...
            def chat(self) -> dubbo.BidiStream[Question, Answer]: ...

    Implementations serve an ``async def`` taking the stream last:
    `SendStream` for the responses of a server stream, `ReceiveStream` for
    the requests of a client stream, or `Stream` for both::

        @dubbo.service("com.example.UserService")
        class UserServiceImpl:
            async def rename(self, id: int, name: str) -> None: ...
            async def watch(self, query: Query, events: dubbo.SendStream[Event]) -> None: ...
            async def upload(self, chunks: dubbo.ReceiveStream[Chunk]) -> int: ...
            async def chat(self, stream: dubbo.Stream[Answer, Question]) -> None: ...

    Subclasses implement the contract of their class: an implementation of
    a ``typing.Protocol`` or of an abstract class implements every method
    the contract declares. Parameters must be passable both by position
    and by name, since arguments travel in order and some formats name
    them. Methods keep their Python names on the wire unless `method` gives
    them another. Classes generated from IDL by `dubbo.protoc` are contracts
    too: ``Greeter`` for callers and ``GreeterServicer`` for implementations.

    What types travel depends on the serialization of the service: with the
    default ``protobuf``, each method takes one protobuf message and returns
    one, as generated contracts do; with ``hessian2``, values of annotated
    Python types travel as Java objects.

    The methods are read on first use, by `get_definition`, so annotations may
    refer to the contract and to names defined after it.
    """

    def decorate(cls: C) -> C:
        setattr(cls, _SERVICE_ATTRIBUTE, _ServiceDeclaration(interface=interface))
        return cls

    return decorate


def method(name: str) -> Callable[[F], F]:
    """Give a contract method the name it has in other languages.

    Without it, a method keeps its Python name::

        @dubbo.method("getUser")
        async def get_user(self, id: int) -> User: ...

    Raises:
        ValueError: ``name`` is empty.
    """
    if not name:
        raise ValueError("method name must not be empty")

    def decorate(function: F) -> F:
        setattr(function, _METHOD_ATTRIBUTE, _MethodDeclaration(name=name))
        return function

    return decorate


def get_definition(contract: object) -> Service:
    """Return the definition of a service contract, or of the contract an object implements.

    The definition is built on first use and kept.

    Raises:
        TypeError: ``contract`` is not and does not implement a service
            contract, or the contract declares a member that cannot be a
            method, or leaves a type unannotated or unresolvable.
        ValueError: The contract gives two methods the same name.
    """
    return _built(contract).service


def get_contract_methods(contract: object) -> Mapping[str, Method]:
    """Return the methods callers call through a service contract, by the attributes that declare them.

    The keys are the Python names, such as ``get_user``, in the order of
    the methods of `get_definition`.

    Raises:
        TypeError: As `get_definition` raises, or the contract declares how
            its streaming methods are served rather than called.
        ValueError: As `get_definition` raises.
    """
    built = _built(contract)
    if built.view is _View.IMPLEMENTATION:
        raise TypeError(
            f"{built.contract.__qualname__} declares how its streaming methods are served; "
            "call the service through the contract that declares how they are called"
        )

    return built.methods


def get_contract(cls: type) -> type | None:
    """Return the service contract ``cls`` is or implements, if any."""
    return next((k for k in cls.__mro__ if _SERVICE_ATTRIBUTE in vars(k)), None)


def check_handler(method: Method, handler: object, where: str) -> None:
    """Check that ``handler`` can serve ``method``.

    Raises:
        TypeError: It is not an ``async def`` taking the arguments of the method.
    """
    function = handler.func if isinstance(handler, functools.partial) else handler
    if not inspect.iscoroutinefunction(function):
        raise TypeError(f"{where} must be an async def")

    try:
        inspect.signature(cast(Callable[..., Any], handler)).bind(*[None] * arity(method))
    except TypeError as error:
        raise TypeError(f"{where} does not take the arguments of a {method.rpc_type.value} method: {error}") from None


def arity(method: Method) -> int:
    """Return how many arguments the handler of ``method`` takes."""
    match method.rpc_type:
        case RpcType.UNARY:
            return len(method.request)
        case RpcType.SERVER_STREAM:
            # The request, then the response stream.
            return 2
        case _:
            return 1


def _built(contract: object) -> _Built:
    cls = contract if isinstance(contract, type) else type(contract)
    found = get_contract(cls)
    if found is None:
        raise TypeError(f"{cls.__qualname__} is not a service contract; declare it with @dubbo.service")

    built = vars(found).get(_DEFINITION_ATTRIBUTE)
    if built is None:
        built = _build(found)
        setattr(found, _DEFINITION_ATTRIBUTE, built)

    return built


def _build(contract: type) -> _Built:
    declaration: _ServiceDeclaration = vars(contract)[_SERVICE_ATTRIBUTE]
    methods: dict[str, Method] = {}
    views: set[_View] = set()
    for name, (method, view) in _methods(contract):
        methods[name] = method
        if view is not None:
            views.add(view)

    if len(views) > 1:
        raise TypeError(
            f"{contract.__qualname__} declares some streaming methods as called and others as served; "
            "declare each side in its own class"
        )

    return _Built(
        contract=contract,
        service=Service(interface=declaration.interface, methods=tuple(methods.values())),
        methods=MappingProxyType(methods),
        view=next(iter(views), None),
    )


def _implemented(implementation: object, contract: type, attribute_name: str, method: Method) -> Method:
    where = f"{type(implementation).__qualname__}.{attribute_name}"

    # A method of a protocol, or an abstract method, only declares the method.
    attribute = inspect.getattr_static(implementation, attribute_name, None)
    owner = next(base for base in contract.__mro__ if attribute_name in vars(base))
    declared = attribute is vars(owner)[attribute_name] and (
        typing.Protocol in owner.__bases__ or getattr(attribute, "__isabstractmethod__", False)
    )
    if attribute is None or declared:
        raise TypeError(f"{where} is not implemented")

    handler = getattr(implementation, attribute_name)
    check_handler(method, handler, where)
    return attrs.evolve(method, handler=handler)


def _methods(cls: type) -> Iterator[tuple[str, tuple[Method, _View | None]]]:
    # The members of the bases first, each in the place it is first declared, a subclass's member replacing one.
    members: dict[str, object] = {}
    for base in reversed(cls.__mro__):
        for name in inspect.get_annotations(base):
            if not name.startswith("_"):
                raise TypeError(f"{cls.__qualname__}.{name} must be a method")
        members.update(vars(base))

    for name, member in members.items():
        if not name.startswith("_"):
            yield name, _method(cls, name, member)


def _method(cls: type, name: str, member: object) -> tuple[Method, _View | None]:
    """Return the method ``member`` declares, and the side it declares its streams for, if any."""
    where = f"{cls.__qualname__}.{name}"
    if not inspect.isfunction(member):
        raise TypeError(f"{where} must be a method")

    declaration = getattr(member, _METHOD_ATTRIBUTE, None) or _MethodDeclaration(name=name)

    try:
        # Resolves the names inside annotations too, as in ServerStream["Event"].
        hints = typing.get_type_hints(member, include_extras=True)
    except NameError as error:
        raise TypeError(f"{where} has an annotation that cannot be resolved: {error}") from None
    signature = inspect.signature(member)
    if not signature.parameters:
        raise TypeError(f"{where} must take self")

    parameters = [
        parameter.replace(annotation=hints.get(parameter.name, parameter.empty))
        for parameter in list(signature.parameters.values())[1:]
    ]
    for parameter in parameters:
        if parameter.kind is not parameter.POSITIONAL_OR_KEYWORD:
            raise TypeError(
                f"{where} cannot take {parameter.kind.description} parameter {parameter.name!r}; "
                "parameters must be passable by position and by name"
            )
        if parameter.annotation is parameter.empty:
            raise TypeError(f"{where} must annotate the type of parameter {parameter.name!r}")

    response = hints.get("return", signature.empty)
    if response is signature.empty:
        raise TypeError(f"{where} must annotate its return type")
    if response is NoneType:
        response = None

    call_type = _stream_type(response, _CALL_TYPES)
    if not inspect.iscoroutinefunction(member):
        if call_type is None:
            raise TypeError(
                f"{where} must be an async def, or a def returning dubbo.ServerStream, dubbo.ClientStream "
                "or dubbo.BidiStream"
            )
        return _called(where, declaration.name, call_type, parameters, get_args(response)), _View.CALLER

    if call_type is not None:
        raise TypeError(f"{where} returns a stream, so it must be a def, not an async def")

    if any(_stream_type(parameter.annotation, _HANDLER_STREAM_TYPES) for parameter in parameters):
        return _served(where, declaration.name, parameters, response), _View.IMPLEMENTATION

    method = Method(
        name=declaration.name,
        rpc_type=RpcType.UNARY,
        request=tuple(Parameter(name=p.name, type=p.annotation, default=p.default) for p in parameters),
        response=response,
    )
    return method, None


def _stream_type(annotation: Any, types: Mapping[type, RpcType]) -> RpcType | None:
    return types.get(get_origin(annotation) or annotation)


def _called(
    where: str,
    name: str,
    rpc_type: RpcType,
    parameters: list[inspect.Parameter],
    types: tuple[Any, ...],
) -> Method:
    """Return the method a contract for callers declares."""
    if not types:
        raise TypeError(f"{where} must give the message types of the stream it returns")

    # A server stream takes its request as a parameter; the other streams
    # send their requests on the stream.
    if rpc_type is RpcType.SERVER_STREAM:
        if len(parameters) != 1:
            raise TypeError(f"{where} must take exactly one request parameter")

        (response,) = types
        request = Parameter(name=parameters[0].name, type=parameters[0].annotation, default=parameters[0].default)
    else:
        if parameters:
            raise TypeError(f"{where} must take no parameters; its requests are sent on the stream")

        request_type, response = types
        request = Parameter(name="message", type=request_type)

    return Method(name=name, rpc_type=rpc_type, request=(request,), response=response)


def _served(where: str, name: str, parameters: list[inspect.Parameter], returns: Any) -> Method:
    """Return the method a contract for implementations declares."""
    *requests, stream = parameters
    rpc_type = _stream_type(stream.annotation, _HANDLER_STREAM_TYPES)
    if rpc_type is None or any(_stream_type(p.annotation, _HANDLER_STREAM_TYPES) for p in requests):
        raise TypeError(f"{where} must take one stream, as its last parameter")

    types = get_args(stream.annotation)
    if not types:
        raise TypeError(f"{where} must give the message types of its stream {stream.name!r}")

    # A server stream takes its request, then the stream; the other streams
    # receive their requests on the stream.
    match rpc_type:
        case RpcType.SERVER_STREAM:
            if len(requests) != 1:
                raise TypeError(f"{where} must take exactly one request parameter before its stream")
            request = Parameter(name=requests[0].name, type=requests[0].annotation, default=requests[0].default)
            (response,) = types
        case RpcType.CLIENT_STREAM:
            (request_type,) = types
            request, response = Parameter(name="message", type=request_type), returns
        case _:
            response, request_type = types
            request = Parameter(name="message", type=request_type)

    if rpc_type is not RpcType.SERVER_STREAM and requests:
        raise TypeError(f"{where} must take only its stream; its requests are received on it")
    if rpc_type is not RpcType.CLIENT_STREAM and returns is not None:
        raise TypeError(f"{where} sends its responses on the stream, so it must return None")

    return Method(name=name, rpc_type=rpc_type, request=(request,), response=response)
