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

import contextlib
import datetime
import enum
from collections.abc import Callable, Sequence
from typing import Any

import hessian2

from dubbo.exceptions import RemoteError
from dubbo.url import URL

from .base import Codec, JavaSerialization, Reader

__all__ = ["Hessian2Serialization"]

# How a throwable decodes: an object, or the text some peers send instead.
_THROWABLE = hessian2.HessianObject | str
# What an object being generalized stands for until it is.
_GENERALIZING = object()


class Hessian2Serialization(JavaSerialization):
    """Carry values in Hessian 2.0, the default Dubbo format.

    A class travels under the Java name it declares with
    ``hessian2.java_class``, and ``hessian2.Long`` and the other tags of
    hessian2 name the Java types of values. Values decode as their
    annotations type them; where an annotation takes any value, an object
    decodes as a ``hessian2.HessianObject``.
    """

    content_subtype = "hessian2"
    shared = True

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._codec = hessian2.Codec(unknown_class="hessian_object")

    def codec(self, types: Sequence[Any]) -> Codec[tuple[Any, ...]]:
        codec = self._codec
        throwables = [index for index, annotation in enumerate(types) if annotation is Exception]
        encode_types = tuple(Any if annotation is Exception else annotation for annotation in types)
        decode_types = tuple(_THROWABLE if annotation is Exception else annotation for annotation in types)
        # Decoding nothing prepares the types, which raises TypeError for one hessian2 cannot decode.
        with contextlib.suppress(hessian2.DecodeError):
            codec.loads_many(b"", types=decode_types)

        if not throwables:

            def encode(values: tuple[Any, ...]) -> bytes:
                return codec.dumps_many(values, types=encode_types)

            def decode(data: bytes) -> tuple[Any, ...]:
                return tuple(codec.loads_many(data, types=decode_types))

            return Codec(encode=encode, decode=decode)

        def encode_throwables(values: tuple[Any, ...]) -> bytes:
            converted = list(values)
            for index in throwables:
                converted[index] = _throwable(converted[index])
            return codec.dumps_many(converted, types=encode_types)

        def decode_throwables(data: bytes) -> tuple[Any, ...]:
            values = codec.loads_many(data, types=decode_types)
            for index in throwables:
                values[index] = _remote_error(values[index])
            return tuple(values)

        return Codec(encode=encode_throwables, decode=decode_throwables)

    def reader(self, data: bytes) -> Reader:
        return _Reader(self._codec.reader(data))

    def java_type(self, annotation: Any) -> str | None:
        try:
            return self._codec.java_name(annotation)
        except TypeError:
            return None

    def generalize(self, value: Any, annotation: Any) -> Any:
        # A null stays one, which responses carry as no value.
        if value is not None and annotation is not None and annotation is not Any:
            value = hessian2.Typed(value, annotation)
        return _generalize(self._codec, value, {})


class _Reader:
    __slots__ = ("_reader",)

    def __init__(self, reader: hessian2.Reader) -> None:
        self._reader = reader

    def load(self, type: Any) -> Any:
        try:
            if type is Exception:
                return _remote_error(self._reader.load(type=_THROWABLE))
            return self._reader.load(type=type)
        except EOFError:
            raise ValueError("the message ends before this value") from None


def _generalize(codec: hessian2.Codec, value: Any, seen: dict[int, tuple[Any, Any]]) -> Any:
    """Return ``value`` generalized, or ``value`` itself when nothing within it changes.

    ``seen`` holds each object and collection reached so far, with what it
    became, by its id.
    """
    if isinstance(value, hessian2.Typed):
        if value.type == hessian2.LocalDateTime:
            return _local_date_time(value.value)
        inner = _generalize(codec, value.value, seen)
        if inner is value.value:
            return value
        # An array of objects stays an array, of maps.
        return hessian2.Typed(inner, tuple[Any, ...]) if isinstance(inner, tuple) else inner
    if isinstance(value, dict | list | tuple | set | frozenset):
        return _once(value, seen, lambda: _generalize_items(codec, value, seen))
    # A datetime stands for a java.util.Date, which stays one.
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return _local_time(value)

    obj = codec.as_object(value)
    if obj is None:
        return value
    if isinstance(value, enum.Enum):
        return obj.fields["name"]
    return _once(
        value,
        seen,
        lambda: {
            "class": obj.class_name,
            **{name: _generalize(codec, field, seen) for name, field in obj.fields.items()},
        },
    )


def _generalize_items(
    codec: hessian2.Codec, value: dict | list | tuple | set | frozenset, seen: dict[int, tuple[Any, Any]]
) -> Any:
    if isinstance(value, dict):
        items = {_generalize(codec, key, seen): _generalize(codec, item, seen) for key, item in value.items()}
        return value if all(items.get(key) is item for key, item in value.items()) else items

    generalized = [_generalize(codec, item, seen) for item in value]
    if all(new is old for new, old in zip(generalized, value, strict=True)):
        return value
    try:
        return type(value)(generalized)
    except TypeError:
        # A set of what became maps, which no set holds, travels as a list.
        return generalized


def _once(value: Any, seen: dict[int, tuple[Any, Any]], generalize: Callable[[], Any]) -> Any:
    """Return what ``generalize`` returns for ``value``, computed once for each object however many hold it.

    Raises:
        ValueError: ``value`` holds itself.
    """
    entry = seen.get(id(value))
    if entry is not None:
        if entry[1] is _GENERALIZING:
            raise ValueError(f"a {type(value).__name__} holds itself")
        return entry[1]

    # ``seen`` keeps ``value``, so that no other object takes its id.
    seen[id(value)] = (value, _GENERALIZING)
    generalized = generalize()
    seen[id(value)] = (value, generalized)
    return generalized


def _local_time(value: datetime.time) -> str:
    """Return the text ``java.time.LocalTime.toString`` gives for ``value``: seconds and fractions only when not zero."""
    if value.microsecond:
        return value.isoformat("milliseconds" if value.microsecond % 1000 == 0 else "microseconds")
    return value.isoformat("seconds" if value.second else "minutes")


def _local_date_time(value: datetime.datetime) -> str:
    """Return the text ``java.time.LocalDateTime.toString`` gives for ``value``."""
    return f"{value.date().isoformat()}T{_local_time(value.time())}"


def _throwable(error: Any) -> Any:
    """Return what an exception travels as: an object of its class for a `RemoteError`, else itself."""
    if not isinstance(error, RemoteError):
        return error

    fields = {**error.fields, "detailMessage": error.message or None}
    fields.setdefault("cause", None)
    fields.setdefault("stackTrace", [])
    fields.setdefault("suppressedExceptions", [])
    return hessian2.HessianObject(error.class_name, fields)


def _remote_error(throwable: hessian2.HessianObject | str) -> RemoteError:
    if isinstance(throwable, str):
        return RemoteError("java.lang.Exception", throwable)

    fields = dict(throwable.fields)
    message = fields.pop("detailMessage", None)
    return RemoteError(throwable.class_name, message if isinstance(message, str) else "", fields=fields)
