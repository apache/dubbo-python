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

"""How the protocols that call Java methods name Python types and errors in Java, such as Dubbo and Triple wrapping.

What each Python type stands for in Java comes from the serialization for the
types it declares, and from the rules here for the others.
"""

import collections.abc
import typing
from typing import Annotated, Any

from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.rpc.definition import JavaType, Method
from dubbo.serialization import JavaSerialization
from dubbo.utils.annotations import TYPE_ALIASES, UNIONS

__all__ = [
    "caller_error",
    "java_exception",
    "java_type_name",
    "method_descriptor",
]

# The Java type each Python type stands for when the serialization names none.
_TYPES: dict[Any, str] = {
    bool: "boolean",
    int: "int",
    float: "double",
    str: "java.lang.String",
    bytes: "[B",
    Any: "java.lang.Object",
    object: "java.lang.Object",
    Exception: "java.lang.Throwable",
    None: "void",
}
_COLLECTIONS: dict[Any, str] = {
    **dict.fromkeys(
        (list, collections.abc.Sequence, collections.abc.MutableSequence, collections.abc.Collection),
        "java.util.List",
    ),
    **dict.fromkeys((set, frozenset, collections.abc.Set, collections.abc.MutableSet), "java.util.Set"),
    **dict.fromkeys((dict, collections.abc.Mapping, collections.abc.MutableMapping), "java.util.Map"),
}
# The box of each primitive, which ``X | None`` stands for.
_BOXES = {
    "boolean": "java.lang.Boolean",
    "byte": "java.lang.Byte",
    "char": "java.lang.Character",
    "short": "java.lang.Short",
    "int": "java.lang.Integer",
    "long": "java.lang.Long",
    "float": "java.lang.Float",
    "double": "java.lang.Double",
}
# The descriptor of each primitive, from the Java Virtual Machine Specification, 4.3.2.
_PRIMITIVE_DESCRIPTORS = {
    "boolean": "Z",
    "byte": "B",
    "char": "C",
    "short": "S",
    "int": "I",
    "long": "J",
    "float": "F",
    "double": "D",
}


# The exception a status travels as, and the class of an exception from Python that names none.
_RPC_EXCEPTION = "org.apache.dubbo.rpc.RpcException"
_RUNTIME_EXCEPTION = "java.lang.RuntimeException"
# The code of RpcException for each status, and the status of each code, shared with every language.
_CODES: dict[Status, int] = {
    Status.DEADLINE_EXCEEDED: 2,  # TIMEOUT_EXCEPTION
    Status.PERMISSION_DENIED: 4,  # FORBIDDEN_EXCEPTION
    Status.UNAVAILABLE: 1,  # NETWORK_EXCEPTION
    Status.UNIMPLEMENTED: 11,  # METHOD_NOT_FOUND
}
_UNKNOWN_EXCEPTION = 0
_STATUSES: dict[int, Status] = {
    2: Status.DEADLINE_EXCEEDED,  # TIMEOUT_EXCEPTION
    8: Status.DEADLINE_EXCEEDED,  # TIMEOUT_TERMINATE
    4: Status.PERMISSION_DENIED,  # FORBIDDEN_EXCEPTION
    13: Status.UNAUTHENTICATED,  # AUTHORIZATION_EXCEPTION
    7: Status.UNAVAILABLE,  # LIMIT_EXCEEDED_EXCEPTION
    1: Status.UNAVAILABLE,  # NETWORK_EXCEPTION
    11: Status.UNIMPLEMENTED,  # METHOD_NOT_FOUND
    5: Status.INTERNAL,  # SERIALIZATION_EXCEPTION
}


def method_descriptor(serialization: JavaSerialization, method: Method) -> str:
    """Return the descriptor of the parameters of ``method``, such as ``Ljava/lang/String;J``.

    A Java provider finds the method by its name and this descriptor, so it
    must match the Java declaration exactly; `java_type_name` gives the Java
    type of each parameter.

    Raises:
        TypeError: A parameter has a type with no Java type.
    """
    try:
        return "".join(_descriptor(java_type_name(serialization, parameter.type)) for parameter in method.request)
    except TypeError as error:
        raise TypeError(f"{method.name} has a parameter with no Java type: {error}") from None


def java_type_name(serialization: JavaSerialization, annotation: Any) -> str:
    """Return the Java type a value of ``annotation`` stands for, named as ``Class.getName`` names it.

    The serialization names the types it declares, such as ``com.example.User``
    for a class it carries under that name. Of the others, ``int``, ``bool``
    and ``float`` stand for ``int``, ``boolean`` and ``double``, and each of
    them ``| None`` for its box, such as ``java.lang.Integer``; ``str`` and
    ``bytes`` for ``java.lang.String`` and ``byte[]``, ``tuple[X, ...]`` for
    an array, lists, sets and dicts for ``java.util.List``, ``Set`` and
    ``Map``, ``Any`` for ``java.lang.Object``, ``Exception`` for
    ``java.lang.Throwable``, and ``None``, the response of a method that
    returns nothing, for ``void``. A `JavaType` in the metadata of an
    ``Annotated`` names the type over all of these.

    Raises:
        TypeError: ``annotation`` has no Java type.
    """
    if isinstance(annotation, TYPE_ALIASES):
        return java_type_name(serialization, annotation.__value__)
    if typing.get_origin(annotation) is Annotated:
        named = [metadata for metadata in annotation.__metadata__ if isinstance(metadata, JavaType)]
        if named:
            return named[-1].name
    name = serialization.java_type(annotation)
    if name is not None:
        return name
    if annotation in _TYPES:
        return _TYPES[annotation]
    if annotation in _COLLECTIONS:
        return _COLLECTIONS[annotation]

    origin = typing.get_origin(annotation)
    if origin in UNIONS:
        members = [member for member in typing.get_args(annotation) if member is not type(None)]
        if len(members) != 1:
            raise TypeError(f"{annotation!r} names several Java types")
        name = java_type_name(serialization, members[0])
        return _BOXES.get(name, name)
    if origin is Annotated:
        return java_type_name(serialization, annotation.__origin__)
    if origin is tuple:
        arguments = typing.get_args(annotation)
        if len(arguments) != 2 or arguments[1] is not Ellipsis:
            raise TypeError(f"{annotation!r} is no Java array; write tuple[X, ...]")
        component = java_type_name(serialization, arguments[0])
        return "[" + (component if component.startswith("[") else _descriptor(component).replace("/", "."))
    if origin in _COLLECTIONS:
        return _COLLECTIONS[origin]

    raise TypeError(f"{annotation!r} has no Java type")


def java_exception(serialization: JavaSerialization, error: Exception) -> Exception:
    """Return the exception a Java caller receives when a handler raises ``error``.

    A `RemoteError`, and an exception of a class the serialization declares,
    travel as they are. Another `RpcError` travels as an
    ``org.apache.dubbo.rpc.RpcException`` whose ``code`` stands for its
    status, and any other exception as a ``java.lang.RuntimeException``
    naming its Python class.
    """
    if isinstance(error, RemoteError):
        return error
    if isinstance(error, RpcError):
        code = _CODES.get(error.status, _UNKNOWN_EXCEPTION)
        return RemoteError(_RPC_EXCEPTION, error.message, fields={"code": code}, status=error.status)
    if serialization.java_type(type(error)) is not None:
        return error

    return RemoteError(_RUNTIME_EXCEPTION, f"{type(error).__name__}: {error}")


def caller_error(error: RemoteError) -> RemoteError:
    """Return the error a caller receives for a Java exception: an ``RpcException`` takes the status of its code."""
    if error.class_name != _RPC_EXCEPTION:
        return error

    code = error.fields.get("code")
    status = _STATUSES.get(code, Status.UNKNOWN) if isinstance(code, int) else Status.UNKNOWN
    return RemoteError(error.class_name, error.message, fields=error.fields, status=status)


def _descriptor(name: str) -> str:
    """Return the descriptor of a Java type named as ``Class.getName`` names it, such as ``J`` for ``long``."""
    if name in _PRIMITIVE_DESCRIPTORS:
        return _PRIMITIVE_DESCRIPTORS[name]

    internal = name.replace(".", "/")
    return internal if internal.startswith("[") else f"L{internal};"
