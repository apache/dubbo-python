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
from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar

import attrs

from dubbo.constants import DEFAULT_JAVA_SERIALIZATION, DEFAULT_SERIALIZATION, SERIALIZATION_KEY
from dubbo.extension import extension_point, extensions
from dubbo.url import URL

__all__ = ["Codec", "JavaSerialization", "Reader", "Serialization", "get_java_serialization", "get_serialization"]

T = TypeVar("T")


@attrs.define(frozen=True, kw_only=True)
class Codec(Generic[T]):
    """Turns one kind of message into bytes and back.

    Attributes:
        encode: Returns the bytes of a message; raises `TypeError` for a
            value the codec cannot carry.
        decode: Returns the message the bytes hold; raises `ValueError` for
            bytes that hold none.
    """

    encode: Callable[[T], bytes]
    decode: Callable[[bytes], T]


@extension_point("apache_dubbo.serialization")
class Serialization(typing.Protocol):
    """A message format, such as ``protobuf``.

    It turns values into bytes and back; each protocol decides which values
    a message holds. Codecs are made once for each method, when a service is
    exported or a method is first called, so that a call only encodes and
    decodes. Codecs run in the event loop for every message, concurrently
    for many calls, so they keep no state between messages and must be quick.

    Attributes:
        content_subtype: Names the format in a content type, such as
            ``proto`` in ``application/grpc+proto``.
        shared: Whether a protocol may make one instance for each name and
            share it, with its codecs, among the services that name it,
            from the URL of the first; false by default, which makes one
            instance for each service from its own URL. A format that reads
            settings of a service from ``url`` leaves it false.
    """

    content_subtype: typing.ClassVar[str]
    shared: typing.ClassVar[bool] = False

    def __init__(self, url: URL) -> None: ...

    def codec(self, types: Sequence[Any]) -> Codec[tuple[Any, ...]]:
        """Return the codec of one value of each type annotation in ``types``, in order.

        It decodes each value as its annotation types it, and raises
        `ValueError` for bytes that do not hold one value of each type. An
        annotation of `typing.Any` takes any value the format describes
        itself.

        Raises:
            TypeError: The format cannot carry values of ``types``.
        """
        ...


class Reader(typing.Protocol):
    """Reads the values of one message one at a time, so that a value can decide the types of those after it."""

    def load(self, type: Any) -> Any:
        """Return the next value, decoded as the annotation ``type`` types it.

        Raises:
            ValueError: No value is left, or the next one is not of ``type``;
                the reader cannot go on.
        """
        ...


@typing.runtime_checkable
class JavaSerialization(Serialization, typing.Protocol):
    """A format of Java objects, whose objects travel with the names of their Java classes, such as ``hessian2``.

    The protocols that call Java methods, such as Dubbo, carry their values
    in one. It names the Java types of the annotations it declares, and reads
    values one at a time. An `Exception` annotation stands for a Java
    throwable: a `RemoteError` travels as an object of its class, an
    exception of a class the format declares as that class, and any
    throwable received decodes as a `RemoteError`.
    """

    def reader(self, data: bytes) -> Reader:
        """Return a reader of the values ``data`` holds."""
        ...

    def java_type(self, annotation: Any) -> str | None:
        """Return the Java type values of ``annotation`` travel as, named as ``Class.getName`` names it.

        Such as ``long`` or ``com.example.User``. It names the types the format
        declares; for another, such as ``int``, which stands for several Java
        types, it returns ``None``.
        """
        ...

    def generalize(self, value: Any, annotation: Any) -> Any:
        """Return ``value``, of the type ``annotation``, as data that names its classes instead of being of them.

        An object becomes a dict of its fields, by the names they travel
        under, with the Java name of its class under ``"class"``; an enum
        becomes its name. A date, a time and a datetime that travels as a
        ``java.time.LocalDateTime`` become their ISO 8601 text, as
        ``java.time`` writes it; another datetime stays a date. Lists,
        tuples, sets and dicts become those of what their items become, a
        set whose items become dicts a list; other values stay as they are.
        An object held in several places is generalized once. The data
        encodes with the Java types ``value`` encodes with, such as ``long``
        for a field that declares it.

        Raises:
            TypeError: The format cannot carry a value within ``value``.
            ValueError: An object or collection within ``value`` holds itself.
        """
        ...


def get_serialization(url: URL) -> Serialization:
    """Return the serialization that the ``serialization`` parameter of ``url`` names, ``protobuf`` when absent.

    Raises:
        ExtensionError: No implementation has that name.
    """
    name = url.parameters.get(SERIALIZATION_KEY, DEFAULT_SERIALIZATION)
    return extensions.get(Serialization, name)(url)


def get_java_serialization(url: URL) -> JavaSerialization:
    """Return the format of Java objects that the ``serialization`` parameter of ``url`` names, ``hessian2`` when absent.

    Raises:
        ExtensionError: No implementation has that name.
        ValueError: The serialization it names is no format of Java objects,
            such as ``protobuf``.
    """
    name = url.parameters.get(SERIALIZATION_KEY, DEFAULT_JAVA_SERIALIZATION)
    serialization = extensions.get(Serialization, name)(url)
    if not isinstance(serialization, JavaSerialization):
        raise ValueError(f"the serialization {name!r} does not carry Java objects, as hessian2 does")

    return serialization
