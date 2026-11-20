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

"""Generic calls in a format of Java objects: ``$invoke`` naming the method called, in each mode it can take."""

import dataclasses
import datetime
import enum
import functools
import types
import typing
from collections.abc import Collection, Mapping, Sequence
from typing import Any

import attrs

from dubbo.constants import DEFAULT_GENERIC, GENERIC_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.definition import Method, Parameter, RpcType, Service
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.serialization import JavaSerialization
from dubbo.utils.annotations import TYPE_ALIASES, UNIONS

from .java import java_type_name

__all__ = ["GENERIC_INVOKE", "GenericInvoker", "builtin_methods", "invoke_arguments"]

# A generic call carries the method name, the Java parameter types or null, then the arguments or null for none.
GENERIC_INVOKE = Method(
    name="$invoke",
    request=(
        Parameter(name="method", type=str),
        Parameter(name="types", type=tuple[str, ...] | None),
        Parameter(name="arguments", type=tuple[Any, ...] | None),
    ),
    response=Any,
)
# The method names that serve generic calls.
_GENERIC_METHODS = (GENERIC_INVOKE, attrs.evolve(GENERIC_INVOKE, name="$invokeAsync"))
# The echo method, which returns its argument.
_ECHO = Method(name="$echo", request=(Parameter(name="value", type=Any),), response=Any)

# The annotations of the java.time values a generic call carries as text: LocalDate, LocalDateTime and LocalTime.
_TIMES = (datetime.date, datetime.datetime, datetime.time)


def invoke_arguments(serialization: JavaSerialization, method: Method, arguments: tuple[Any, ...]) -> tuple[Any, ...]:
    """Return the arguments of `GENERIC_INVOKE` that call ``method`` with ``arguments``.

    The Java parameter types are ``None`` when the parameters are all `Any`,
    which leaves the provider to find the method by its name.
    """
    if all(parameter.type is Any for parameter in method.request):
        return method.name, None, arguments

    return method.name, tuple(java_type_name(serialization, parameter.type) for parameter in method.request), arguments


def builtin_methods(
    definition: Service, invoke: Invoke, serialization: JavaSerialization
) -> list[tuple[Method, Invoke]]:
    """Return the methods every service serves in a format of Java objects, with what serves each, but those ``definition`` declares.

    ``$invoke`` and ``$invokeAsync`` call a unary method of ``definition`` by
    name through ``invoke``, as a `GenericInvoker` serves them, and
    ``$echo`` returns its argument.
    """
    generic = GenericInvoker(invoke, definition, serialization)
    declared = {method.name for method in definition.methods}
    builtins = [*((method, generic.invoke) for method in _GENERIC_METHODS), (_ECHO, _echo)]
    return [(method, serve) for method, serve in builtins if method.name not in declared]


class GenericInvoker:
    """Serves the generic calls of the unary methods of a service, each naming the method it calls.

    It takes an invocation of `GENERIC_INVOKE` and calls ``invoke`` with one
    of the method named, as a call of the contract would, with the mode of its
    ``generic`` attachment, ``true`` when absent. A call of a mode it does
    not serve, or of a method the service has not, fails with UNIMPLEMENTED,
    and one whose arguments stand for none of the method with
    INVALID_ARGUMENT. Of the modes, it serves ``true``: objects travel as maps
    naming their Java class under ``"class"``, filled into the classes the
    parameters declare; enums travel as their names, and the dates and times
    of java.time as the text of their ``toString``.
    """

    def __init__(self, invoke: Invoke, service: Service, serialization: JavaSerialization) -> None:
        self._invoke = invoke
        self._interface = service.interface
        self._methods = {method.name: method for method in service.methods if method.rpc_type is RpcType.UNARY}
        self._serialization = serialization
        self._any = serialization.codec((Any,))
        # The arguments of each method, decoded as its parameters type them, which fills a class from a map.
        self._arguments = {
            method.name: serialization.codec((types.GenericAlias(tuple, tuple(p.type for p in method.request)),))
            for method in self._methods.values()
        }

    async def invoke(self, invocation: Invocation) -> Result:
        name, _, arguments = invocation.arguments
        mode = invocation.attachments.get(GENERIC_KEY) or DEFAULT_GENERIC
        if mode != DEFAULT_GENERIC:
            return Result(error=RpcError(Status.UNIMPLEMENTED, f"generic calls of the mode {mode!r} are not served"))
        method = self._methods.get(name)
        if method is None:
            return Result(error=RpcError(Status.UNIMPLEMENTED, f"{self._interface} has no unary method {name!r}"))

        try:
            arguments = self._realize(method, arguments or ())
        except (TypeError, ValueError) as error:
            message = f"the arguments of {name} stand for none of its parameters: {error}"
            return Result(error=RpcError(Status.INVALID_ARGUMENT, message))
        called = attrs.evolve(invocation, method=name, definition=method, arguments=arguments, generic=mode)
        result = await self._invoke(called)
        if result.error is not None:
            return result

        try:
            value = self._serialization.generalize(result.value, method.response)
        except (TypeError, ValueError) as error:
            message = f"cannot return the result of {name} generically: {error}"
            return Result(error=RpcError(Status.INTERNAL, message), attachments=result.attachments)
        return attrs.evolve(result, value=value)

    def _realize(self, method: Method, arguments: Sequence[Any]) -> tuple[Any, ...]:
        """Return the arguments of ``method`` that ``arguments``, as the call sent them, stand for.

        Raises:
            TypeError: ``arguments`` cannot be read as the parameters.
            ValueError: ``arguments`` stand for no arguments of ``method``.
        """
        named = tuple(
            _restore(argument, parameter.type) for argument, parameter in zip(arguments, method.request, strict=True)
        )
        return self._arguments[method.name].decode(self._any.encode((named,)))[0]


async def _echo(invocation: Invocation) -> Result:
    return Result(value=invocation.arguments[0])


def _restore(value: Any, annotation: Any) -> Any:
    """Return ``value``, which stands for a value of ``annotation``, with the enum names and the java.time texts within it as the values they name.

    Raises:
        ValueError: A name is of no member of its enum, a text is of no
            date or time, or a fixed-length tuple has another length.
    """
    if isinstance(annotation, TYPE_ALIASES):
        return _restore(value, annotation.__value__)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return _restore(value, args[0])
    if origin in UNIONS:
        arms = [arm for arm in args if arm is not type(None)]
        enums = [arm for arm in arms if isinstance(arm, type) and issubclass(arm, enum.Enum)]
        if isinstance(value, str) and enums:
            return _restore(value, enums[0])

        return _restore(value, arms[0]) if len(arms) == 1 else value
    if isinstance(value, str) and annotation in _TIMES:
        # A java.time value travels as the text of its toString, which is ISO 8601.
        return annotation.fromisoformat(value)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        if not isinstance(value, str):
            return value
        try:
            return annotation[value]
        except KeyError:
            raise ValueError(f"{value!r} is no member of {annotation.__name__}") from None
    if isinstance(value, dict):
        if _is_collection(origin, Mapping) and args:
            return {_restore(k, args[0]): _restore(item, args[1]) for k, item in value.items()}
        if isinstance(annotation, type) and (dataclasses.is_dataclass(annotation) or attrs.has(annotation)):
            fields = _field_types(annotation)
            return {key: _restore(item, fields[key]) if key in fields else item for key, item in value.items()}
        return value
    if isinstance(value, list | tuple | set | frozenset) and _is_collection(origin, Collection) and args:
        if origin is tuple and args[-1] is not Ellipsis:
            return [_restore(v, a) for v, a in zip(value, args, strict=True)]
        return [_restore(v, args[0]) for v in value]

    return value


def _is_collection(origin: Any, kind: type) -> bool:
    return isinstance(origin, type) and issubclass(origin, kind)


@functools.cache
def _field_types(cls: type) -> dict[str, Any]:
    """Return the annotations of the fields of ``cls``, by their Python names and the camelCase names they travel under.

    The camelCase name of ``_main_color`` is ``_mainColor``.
    """
    hints = typing.get_type_hints(cls, include_extras=True)
    fields = {}
    for name, hint in hints.items():
        fields[name] = hint
        core = name.lstrip("_")
        first, *rest = core.split("_")
        fields[name[: len(name) - len(core)] + first + "".join(part[:1].upper() + part[1:] for part in rest)] = hint
    return fields
