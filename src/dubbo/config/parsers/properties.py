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

import re

from dubbo.config.data import ConfigData, insert_path
from dubbo.config.exceptions import ConfigParseError
from dubbo.config.fields import decode_json
from dubbo.config.models import DubboConfig
from dubbo.utils import require_optional_dependency

with require_optional_dependency("dotproperties", extra="properties"):
    import dotproperties

from .base import ConfigParser

__all__ = ["PropertiesParser"]


# A segment of a key: in brackets, which may hold dots, or up to the next dot or bracket.
_SEGMENT = re.compile(r"\[([^\[\]]+)\]|([^.\[\]]+)")


class PropertiesParser(ConfigParser):
    """Reads Java properties, nesting dotted keys: ``a.b=1`` becomes ``{"a": {"b": "1"}}``.

    A segment in brackets keeps its dots, as Spring Boot writes map keys, so
    that a service is named whole: ``provider.services[com.example.Greeter].timeout``,
    or ``provider.services.[com.example.Greeter].timeout``. A value where
    the configuration expects a list, a mapping or a section holds JSON, as
    an environment variable does:
    ``consumer.references[com.example.Echo].urls=["tri://127.0.0.1:50051"]``.
    Other values stay strings. An invalid escape, an empty key segment, an
    unclosed bracket, a key that is both a value and a section, or such a
    value that is not JSON raises ConfigParseError.
    """

    def loads(self, text: str, /) -> ConfigData:
        try:
            flat = dotproperties.loads(text)
        except ValueError as error:
            raise ConfigParseError("invalid properties configuration") from error

        result: dict[str, object] = {}
        key = ""
        try:
            for key, value in flat.items():
                insert_path(result, _segments(key), value)
        except ValueError as error:
            raise ConfigParseError(f"invalid properties key {key!r}: {error}") from None

        try:
            return decode_json(result, DubboConfig)
        except ValueError as error:
            raise ConfigParseError(f"invalid properties configuration: {error}") from error.__cause__


def _segments(key: str) -> list[str]:
    """Split ``key`` at the dots outside brackets: ``a[b.c].d`` and ``a.[b.c].d`` are ``a``, ``b.c`` and ``d``.

    Raises:
        ValueError: A segment is empty or a bracket is not closed.
    """
    segments = []
    position = 0
    while True:
        found = _SEGMENT.match(key, position)
        if found is None:
            raise ValueError(f"no key segment at position {position}")
        segments.append(found[1] if found[1] is not None else found[2])
        position = found.end()
        if position == len(key):
            return segments
        if key[position] == ".":
            position += 1
        elif key[position] != "[":
            raise ValueError(f"no key segment at position {position}")
