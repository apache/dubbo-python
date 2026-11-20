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
import ssl
from collections.abc import Mapping
from typing import TypeVar, cast

import cattrs
from cattrs.v import format_exception

from dubbo.utils.converters import boolean

from .data import ConfigData
from .exceptions import ConfigError

__all__ = ["structure_config", "unstructure_config"]

T = TypeVar("T")


def structure_config(data: ConfigData, cls: type[T], *, path: str = "config") -> T:
    """Build a configuration object of type ``cls`` from merged data, found at ``path`` for the error messages.

    Raises:
        ConfigError: Unknown keys, wrong types, invalid values or undefined
            references. The message names the path of each problem.
    """
    if not isinstance(data, Mapping):
        raise ConfigError(f"invalid configuration: expected a mapping, got {type(data).__name__} @ {path}")

    try:
        return _converter.structure(data, cls)
    except cattrs.BaseValidationError as error:
        # Each problem on a line of its own; the message holds all that the nested cattrs errors tell.
        details = "".join(
            f"\n  {detail}" for detail in cattrs.transform_error(error, path=path, format_exception=_describe)
        )
        raise ConfigError(f"invalid configuration:{details}") from None


def unstructure_config(value: object) -> object:
    """Turn configuration objects into plain data, leaving out unset fields.

    ``None`` marks a field as unset, so it is dropped rather than merged over
    a value from a lower layer.
    """
    return _without_unset(_converter.unstructure(value))


def _without_unset(data: object) -> object:
    if not isinstance(data, dict):
        return data
    items = cast(dict[str, object], data).items()
    return {key: _without_unset(item) for key, item in items if item is not None}


def _describe(error: BaseException, target: type | None) -> str:
    """Format one failure, keeping the messages of validators and hooks.

    The cattrs formatter reduces every TypeError and ValueError to "invalid
    value"; the messages written here and by attrs validators say what is wrong.
    """
    if isinstance(error, (TypeError, ValueError)) and str(error):
        return str(error)
    return format_exception(error, target)


# Hooks accept native values and the strings that environment variables and
# properties files produce, and reject everything else, such as True or 1.5
# for an integer.


def _structure_str(value: object, _: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected a string, got {value!r}")
    return value


def _structure_bool(value: object, _: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return boolean(value.strip())
        except ValueError:
            raise ValueError(f"expected a boolean, got {value!r}") from None
    raise TypeError(f"expected a boolean, got {value!r}")


def _structure_int(value: object, _: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise ValueError(f"expected an integer, got {value!r}") from None
    raise TypeError(f"expected an integer, got {value!r}")


def _structure_float(value: object, _: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            raise ValueError(f"expected a number, got {value!r}") from None
    raise TypeError(f"expected a number, got {value!r}")


def _structure_bool_or_str(value: object, _: object) -> bool | str | None:
    if value is not None and not isinstance(value, (bool, str)):
        raise TypeError(f"expected a boolean or a string, got {value!r}")
    return value


def _structure_enum(value: object, target: type[enum.Enum]) -> enum.Enum:
    try:
        return target(value)
    except ValueError:
        choices = ", ".join(repr(member.value) for member in target)
        raise ValueError(f"expected one of {choices}, got {value!r}") from None


def _structure_ssl_context(value: object, _: object) -> ssl.SSLContext:
    # Only code gives a context; it passes through merging as it is.
    if not isinstance(value, ssl.SSLContext):
        raise TypeError(f"expected an ssl.SSLContext, got {value!r}")
    return value


def _structure_names(value: object, _: object) -> tuple[str, ...]:
    # A bare string is rejected: as an iterable it would split into characters.
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"expected a list of names, got {value!r}")
    return tuple(_structure_str(item, str) for item in cast(list[object], value))


def _structure_parameters(value: object, _: object) -> dict[str, str]:
    # Parameters become URL query values, which are strings; files also write
    # numbers and booleans there, as in "session-timeout: 3000".
    if not isinstance(value, dict):
        raise TypeError(f"expected a mapping of parameters, got {value!r}")

    parameters = {}
    for key, item in cast(dict[object, object], value).items():
        if isinstance(item, bool):
            item = "true" if item else "false"
        elif isinstance(item, (int, float)):
            item = str(item)
        parameters[_structure_str(key, str)] = _structure_str(item, str)
    return parameters


# Unknown keys fail instead of being dropped, so typos surface as errors.
_converter = cattrs.Converter(forbid_extra_keys=True)
_converter.register_structure_hook(str, _structure_str)
_converter.register_structure_hook(bool, _structure_bool)
_converter.register_structure_hook(int, _structure_int)
_converter.register_structure_hook(float, _structure_float)
_converter.register_structure_hook(ssl.SSLContext, _structure_ssl_context)
# StrEnum comes before str in the method resolution order of a string enum.
_converter.register_structure_hook(enum.Enum, _structure_enum)
_converter.register_structure_hook(enum.StrEnum, _structure_enum)
# Predicate registrations: dispatch by class cannot match generic aliases.
_converter.register_structure_hook_func(lambda target: target == tuple[str, ...], _structure_names)
_converter.register_structure_hook_func(lambda target: target == dict[str, str], _structure_parameters)
_converter.register_structure_hook_func(lambda target: target == bool | str | None, _structure_bool_or_str)
