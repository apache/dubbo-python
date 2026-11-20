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

import functools
import inspect
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any, TypeVar, cast

from dubbo.constants import DEFAULT_GENERIC

from .context import attachments_to_send, record_response
from .definition import JavaType, Method, Parameter, RpcType, get_contract_methods, get_definition
from .invocation import Invocation, Invoke, Result

__all__ = ["GenericService", "proxy"]

T = TypeVar("T")

# The forms of generic calls a caller can make in Python.
_GENERIC_MODES = frozenset({DEFAULT_GENERIC, "raw.return", "protobuf-json", "gson"})


def proxy(contract: type[T], invoke: Invoke) -> T:
    """Return an object of type ``contract`` whose methods make their calls with ``invoke``.

    Each method has the name, signature, type annotations and docstring of
    the method of ``contract`` it calls, as `inspect` and
    `typing.get_type_hints` report them.

    Raises:
        TypeError: ``contract`` is not a service contract, or declares how
            its streaming methods are served.
    """
    return cast(T, _Proxy(contract, invoke))


class GenericService:
    """Calls the unary methods of a service by name, without its contract.

    Arguments and results are plain data that the serialization describes
    itself, in the form ``generic`` names, which the provider follows:

    - ``"true"``: objects as dicts naming their Java class under
      ``"class"``, beside lists, strings and numbers;
    - ``"raw.return"``: arguments as for ``"true"``, results as the provider
      returns them;
    - ``"protobuf-json"``: the one argument and the result as the JSON of a
      protobuf message, its type the Java class of the message;
    - ``"gson"``: each argument and the result as JSON.

    Each protocol decides how a generic call travels, such as ``$invoke``
    over Dubbo::

        users = app.refer_generic("com.example.UserService")
        user = await users.call("getUser", "id", 18)

    Raises:
        ValueError: ``generic`` names none of these forms.
    """

    def __init__(self, interface: str, invoke: Invoke, *, generic: str = DEFAULT_GENERIC) -> None:
        if generic not in _GENERIC_MODES:
            raise ValueError(f"generic must be one of {', '.join(sorted(_GENERIC_MODES))}, not {generic!r}")

        self._interface = interface
        self._invoke = invoke
        self._generic = generic

    @property
    def interface(self) -> str:
        """Interface name of the service called, such as ``"com.example.UserService"``."""
        return self._interface

    async def call(self, method: str, /, *arguments: Any, types: Sequence[str] | None = None) -> Any:
        """Call ``method`` with ``arguments`` in parameter order and return its result.

        ``types`` names the Java type of each parameter, as ``Class.getName``
        names it, such as ``["java.lang.String", "long"]``; a Java provider
        needs them to tell apart the methods of one name.

        Raises:
            TypeError: ``types`` does not name one type for each argument.
            RpcError: The call failed; a ``RemoteError`` is the exception the
                method raised.
        """
        if types is None:
            annotations: Sequence[Any] = (Any,) * len(arguments)
        elif isinstance(types, str) or len(types) != len(arguments) or not all(types):
            raise TypeError(f"{method}(): types must name one Java type for each of the {len(arguments)} arguments")
        else:
            annotations = [Annotated[Any, JavaType(name)] for name in types]

        definition = Method(
            name=method,
            request=tuple(
                Parameter(name=f"arg{index}", type=annotation) for index, annotation in enumerate(annotations)
            ),
            response=Any,
        )
        invocation = Invocation(
            interface=self._interface,
            method=method,
            definition=definition,
            arguments=arguments,
            attachments=attachments_to_send(),
            generic=self._generic,
        )
        return _unary_value(await self._invoke(invocation))

    def __repr__(self) -> str:
        return f"<dubbo generic service {self._interface}>"


class _Proxy:
    """Turns method calls on a contract into invocations."""

    def __init__(self, contract: type, invoke: Invoke) -> None:
        methods = get_contract_methods(contract)
        self._definition = get_definition(contract)
        self._invoke = invoke
        self._signatures = {method.name: _signature(method) for method in methods.values()}
        self._attributes = {method.name: attribute for attribute, method in methods.items()}
        # Each method is bound once, so calling it skips __getattr__.
        for attribute, method in methods.items():
            setattr(self, attribute, self._bind(method, getattr(contract, attribute)))

    def __repr__(self) -> str:
        return f"<dubbo proxy {self._definition.interface}>"

    def _bind(self, method: Method, declared: Callable[..., Any]) -> Callable[..., Any]:
        """Return the function that calls ``method``, with the name, signature, annotations and docstring ``declared`` has."""
        if method.rpc_type is RpcType.UNARY:

            async def call(*args: Any, **kwargs: Any) -> Any:
                return _unary_value(await self._invoke(self._invocation(method, self._arguments(method, args, kwargs))))

        else:

            def call(*args: Any, **kwargs: Any) -> Any:
                # Arguments are checked now; the call opens, with the
                # attachments of that moment, when the block is entered.
                return self._open(method, self._arguments(method, args, kwargs))

        functools.update_wrapper(call, declared)
        signature = inspect.signature(declared)
        call.__signature__ = signature.replace(parameters=tuple(signature.parameters.values())[1:])  # ty: ignore[invalid-assignment]
        return call

    @asynccontextmanager
    async def _open(self, method: Method, arguments: tuple[Any, ...]) -> AsyncGenerator[Any]:
        result = await self._invoke(self._invocation(method, arguments))
        if result.error is not None:
            record_response(result.attachments)
            raise result.error

        call = result.value
        try:
            async with call:
                yield call
        finally:
            record_response(call.response_attachments)

    def _arguments(self, method: Method, args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, ...]:
        signature = self._signatures[method.name]
        # Every parameter given by position, in parameter order.
        if not kwargs and len(args) == len(signature.parameters):
            return args

        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError as error:
            raise TypeError(f"{self._attributes[method.name]}(): {error}") from None

        bound.apply_defaults()
        return tuple(bound.arguments.values())

    def _invocation(self, method: Method, arguments: tuple[Any, ...]) -> Invocation:
        return Invocation(
            interface=self._definition.interface,
            method=method.name,
            definition=method,
            arguments=arguments,
            attachments=attachments_to_send(),
        )


def _unary_value(result: Result) -> Any:
    """Return the value of a unary call that ended with ``result``, or raise its error, recording its attachments."""
    record_response(result.attachments)

    if result.error is not None:
        raise result.error

    return result.value


def _signature(method: Method) -> inspect.Signature:
    # Client and bidirectional streams send their requests on the stream, so
    # opening them takes no arguments.
    if method.rpc_type in (RpcType.CLIENT_STREAM, RpcType.BIDI_STREAM):
        return inspect.Signature()

    return inspect.Signature(
        [inspect.Parameter(p.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=p.default) for p in method.request]
    )
