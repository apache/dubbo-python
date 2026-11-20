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

"""How configuration fields meet the outside: the text read into them, and the URL they become.

The environment variable a field declares is an input alias, read when the
configuration loads; the URL parameter is the output, written when the
configuration becomes URLs. A field may declare both, as in
``metadata=env_variable("X") | url_parameter("x")``.
"""

import json
import os
from collections.abc import Callable, Mapping
from typing import Any, cast, get_args, get_origin

import attrs

from dubbo.utils.annotations import UNIONS
from dubbo.utils.converters import to_text

from .data import ConfigData

__all__ = [
    "check_address_keys",
    "check_url_keys",
    "decode_json",
    "env_variable",
    "read_declared_env",
    "to_url_parameters",
    "url_nested",
    "url_parameter",
]

# The metadata keys, namespaced as attrs recommends.
_ENV_VARIABLE = "dubbo.env_variable"
_URL = "dubbo.url"


def env_variable(name: str) -> dict[str, object]:
    """Declare, as ``attrs.field`` metadata, the environment variable that also sets a field.

    ``name`` is unprefixed, as Dubbo in every language reads it, such as
    ``DUBBO_IP_TO_REGISTRY``.
    """
    return {_ENV_VARIABLE: name}


def read_declared_env(cls: type[attrs.AttrsInstance]) -> ConfigData:
    """Read the environment variables that the fields of ``cls``, and of the configurations it nests, declare.

    Values stay strings until the configuration converts them.
    """
    data: dict[str, object] = {}
    for field in attrs.fields(cls):
        name = field.metadata.get(_ENV_VARIABLE)
        nested = _attrs_class(field.type)
        if name is not None and os.environ.get(name):
            data[field.name] = os.environ[name]
        elif nested is not None and (values := read_declared_env(nested)):
            data[field.name] = values

    return data


def decode_json(data: ConfigData, cls: type[attrs.AttrsInstance]) -> ConfigData:
    """Decode the text of ``data`` that stands where ``cls`` expects a mapping, a list or a section, as JSON.

    Other text, and keys that ``cls`` does not know, stay as they are, for
    the configuration to convert or reject.

    Raises:
        ValueError: Such text is not JSON; the message names its path.
    """
    return cast(ConfigData, _decoded(data, cls, ()))


def url_parameter(key: str, encode: Callable[[Any], str] = to_text, *, default: object = None) -> dict[str, object]:
    """Declare, as ``attrs.field`` metadata, that a field becomes the URL parameter ``key``.

    ``encode`` turns a value into the parameter text; by default booleans
    become ``true`` or ``false`` and other values ``str()``. ``default`` is
    the value that ``None`` stands for; when it is ``None`` too, an unset
    field adds no parameter.
    """
    return {_URL: _URLParameter(key, encode, default)}


def url_nested(key: str | None = None) -> dict[str, object]:
    """Declare, as ``attrs.field`` metadata, that the URL parameters of a nested configuration join those of its own.

    With ``key``, each parameter comes after it and a dot, as in
    ``triple.compressor``. A mapping joins each entry under its key: text as
    it is, and a configuration with its parameters after the key and a dot,
    as in ``getUser.timeout``. Declared fields override the text of mappings.
    """
    return {_URL: _URLNested("" if key is None else f"{key}.")}


def to_url_parameters(*configs: attrs.AttrsInstance | None) -> dict[str, str]:
    """Collect the URL parameters that the fields of ``configs`` declare.

    Configurations apply from low to high priority, so a later one overrides
    an earlier one, as a service overrides its provider; ``None`` stands for
    one that sets nothing. A field left as ``None`` keeps the lower value, or
    adds its default if no configuration sets it.
    """
    defaults: dict[str, str] = {}
    extra: dict[str, str] = {}
    declared: dict[str, str] = {}
    for config in configs:
        if config is not None:
            _collect(config, "", defaults, extra, declared)

    return defaults | extra | declared


def check_url_keys(config: attrs.AttrsInstance, parameters: Mapping[str, str]) -> None:
    """Check that ``parameters`` sets no key that a field of ``config`` declares.

    A configuration that overrides others needs it: a field of a lower one
    would override such a parameter.

    Raises:
        ValueError: ``parameters`` sets a key that a field declares.
    """
    for name, declared in _declared(type(config)).items():
        if declared.key in parameters:
            raise ValueError(f"set the {name} field instead of the {declared.key!r} parameter")


def check_address_keys(config: attrs.AttrsInstance, parameters: Mapping[str, str], query: Mapping[str, str]) -> None:
    """Check that the places that set a key of the URL of an address agree.

    The places are a field of ``config`` that is set, its ``parameters`` and
    the ``query`` of its address; a key they set alike is set once. The
    message names the key alone, as a value may be a secret.

    Raises:
        ValueError: Two places set a key to different values.
    """
    for name, declared in _declared(type(config)).items():
        value = getattr(config, name)
        if value is None:
            continue
        encoded = declared.encode(value)
        if parameters.get(declared.key, encoded) != encoded or query.get(declared.key, encoded) != encoded:
            raise ValueError(f"the {name} field and the {declared.key!r} parameter differ")
    for key, value in parameters.items():
        if query.get(key, value) != value:
            raise ValueError(f"parameter {key!r} differs from the one in the address")


@attrs.define(frozen=True)
class _URLParameter:
    key: str
    encode: Callable[[Any], str]
    default: object


@attrs.define(frozen=True)
class _URLNested:
    prefix: str


def _decoded(value: object, target: object, path: tuple[str, ...]) -> object:
    target = _without_none(target)
    nested = _attrs_class(target)
    if isinstance(value, str):
        if nested is None and get_origin(target) not in (dict, list, tuple):
            return value
        try:
            return json.loads(value)
        except ValueError as error:
            raise ValueError(f"the value of {'.'.join(path)!r} must be JSON") from error

    if not isinstance(value, dict):
        return value

    items = cast(dict[str, object], value).items()
    if nested is not None:
        fields = attrs.fields_dict(nested)
        return {key: _decoded(item, fields[key].type, (*path, key)) if key in fields else item for key, item in items}
    if get_origin(target) is dict:
        item_type = get_args(target)[1]
        return {key: _decoded(item, item_type, (*path, key)) for key, item in items}

    return value


def _attrs_class(annotation: object) -> type[attrs.AttrsInstance] | None:
    """Return the attrs class ``annotation`` names, alone or as ``X | None``."""
    annotation = _without_none(annotation)
    return annotation if isinstance(annotation, type) and attrs.has(annotation) else None


def _without_none(annotation: object) -> object:
    """Unwrap ``X | None`` to ``X``; return any other type unchanged."""
    if get_origin(annotation) in UNIONS:
        options = [option for option in get_args(annotation) if option is not type(None)]
        if len(options) == 1:
            return options[0]
    return annotation


def _collect(
    config: attrs.AttrsInstance, prefix: str, defaults: dict[str, str], extra: dict[str, str], declared: dict[str, str]
) -> None:
    for field in attrs.fields(type(config)):
        value = getattr(config, field.name)
        match field.metadata.get(_URL):
            case _URLParameter(key, encode, default):
                if value is not None:
                    declared[prefix + key] = encode(value)
                elif default is not None:
                    defaults[prefix + key] = encode(default)
            case _URLNested(nested):
                _flatten(value, prefix + nested, defaults, extra, declared)


def _flatten(
    value: object, prefix: str, defaults: dict[str, str], extra: dict[str, str], declared: dict[str, str]
) -> None:
    if attrs.has(type(value)):
        _collect(value, prefix, defaults, extra, declared)
    elif isinstance(value, Mapping):
        for key, item in cast(Mapping[str, object], value).items():
            if isinstance(item, str):
                extra[prefix + key] = item
            else:
                _flatten(item, f"{prefix}{key}.", defaults, extra, declared)


def _declared(cls: type[attrs.AttrsInstance]) -> dict[str, _URLParameter]:
    fields = attrs.fields(cls)
    return {field.name: field.metadata[_URL] for field in fields if isinstance(field.metadata.get(_URL), _URLParameter)}
