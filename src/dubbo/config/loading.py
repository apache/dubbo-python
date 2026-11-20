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

import logging
import os
from collections.abc import Iterable, Mapping
from os import PathLike
from pathlib import Path, PurePosixPath
from typing import cast

from dubbo.config_center import ConfigCenter, get_config_center
from dubbo.constants import DEFAULT_CONFIG_CENTER_CHECK, DEFAULT_CONFIG_CENTER_FILE, DEFAULT_CONFIG_CENTER_GROUP
from dubbo.extension import ApplicationScope, ExtensionError, extensions
from dubbo.url import APPLICATION_SCOPE

from .data import ConfigData, insert_path, merge
from .exceptions import ConfigError, ConfigParseError, ConfigReadError
from .fields import decode_json, read_declared_env
from .models import ConfigCenterConfig, DubboConfig, RegistryConfig
from .parsers import ConfigParser, get_parser
from .structure import structure_config, unstructure_config

__all__ = ["ConfigSource", "load_config"]

# A file path, read with the parser for its suffix, or configuration data.
ConfigSource = str | PathLike[str] | Mapping[str, object]

_logger = logging.getLogger(__name__)


async def load_config(
    sources: Iterable[ConfigSource],
    *,
    env_prefix: str | None,
    code: ConfigData,
    scope: ApplicationScope,
) -> DubboConfig:
    """Read, merge and validate the configuration of one application.

    The layers merge from low to high priority: ``sources`` in order, the
    configuration center, the environment variables named with
    ``env_prefix`` unless it is ``None``, then ``code``, the configuration
    set in code as plain data without unset fields.
    The variables that fields declare with ``env_variable``, such as
    ``DUBBO_IP_TO_REGISTRY``, are in the layer of the environment, below the
    prefixed ones.

    The configuration center is set by the other layers, so they are read
    first; when they set none, the first of their registries that serves as
    one is it. The application of ``scope`` keeps it open for its other
    readers.

    Raises:
        ConfigError: The configuration cannot be read or is invalid.
    """
    files = [_read_source(source) for source in sources]
    env = {} if env_prefix is None else _merged(read_declared_env(DubboConfig), _read_prefixed_env(env_prefix))

    # The configuration center is set by the local layers alone, or else is a registry they set.
    local = _merged(*files, env, code)
    center = local.get("config_center")
    config = None
    derived: ConfigData = {}
    if center is not None:
        config = structure_config(cast(ConfigData, center), ConfigCenterConfig, path="config.config_center")
    elif (config := _registry_as_config_center(local)) is not None:
        derived = {"config_center": cast(ConfigData, unstructure_config(config))}
    remote = {} if config is None else await _read_config_center(config, scope)

    return structure_config(_merged(derived, *files, remote, env, code), DubboConfig)


def _registry_as_config_center(local: ConfigData) -> ConfigCenterConfig | None:
    """Return the configuration center of the first registry of ``local`` that serves as one, if any."""
    data = cast(ConfigData, local.get("registries", {}))
    registries = structure_config(data, dict[str, RegistryConfig], path="config.registries")
    kinds = extensions.names(ConfigCenter)
    for name, registry in registries.items():
        use = registry.use_as_config_center
        if use or (use is None and registry.to_url().protocol in kinds):
            try:
                return ConfigCenterConfig.from_registry(registry)
            except ValueError as error:
                raise ConfigError(f"invalid configuration: {error} @ config.registries.{name}") from None
    return None


def _merged(*layers: ConfigData) -> dict[str, object]:
    """Merge layers from low to high priority.

    Mappings merge recursively; any other value, including a list, replaces
    the lower one.
    """
    data: dict[str, object] = {}
    for layer in layers:
        merge(data, layer)
    return data


def _read_file(path: str | PathLike[str]) -> ConfigData:
    """Read one file with the parser named by its suffix.

    Raises:
        ConfigReadError: No parser matches, or the file cannot be read or decoded.
        ConfigParseError: The parser rejects its content.
    """
    path = Path(path)
    parser = _parser(str(path), None)

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ConfigReadError(f"cannot read configuration file {str(path)!r}") from error

    try:
        return parser.loads(text)
    except ConfigParseError as error:
        raise ConfigParseError(f"{error} in {str(path)!r}") from error.__cause__


def _read_source(source: ConfigSource) -> ConfigData:
    return cast(ConfigData, source) if isinstance(source, Mapping) else _read_file(source)


async def _read_config_center(config: ConfigCenterConfig, scope: ApplicationScope) -> ConfigData:
    """Read the configuration stored under ``config_file`` in ``group``.

    The configuration center is the one the application of ``scope``
    shares, which stays open until the application stops.

    Returns:
        The parsed configuration; empty when the entry is missing or blank,
        or cannot be read and ``check`` is false.

    Raises:
        ConfigReadError: No implementation matches the scheme, no parser
            matches ``format`` or the suffix of the key, or the entry cannot
            be read and ``check`` is not false.
        ConfigParseError: The entry has invalid content.
        ConfigError: The entry sets ``config_center``.
    """
    url = config.to_url().replace(attributes={APPLICATION_SCOPE: scope})
    key = config.config_file or DEFAULT_CONFIG_CENTER_FILE
    group = config.group or DEFAULT_CONFIG_CENTER_GROUP
    parser = _parser(key, config.format)
    check = DEFAULT_CONFIG_CENTER_CHECK if config.check is None else config.check

    try:
        center = await get_config_center(url)
        text = await center.get(key, group=group)
    # A missing implementation is a configuration mistake, which check does not excuse.
    except ExtensionError as error:
        raise ConfigReadError(f"cannot load configuration center {url.protocol!r} for {url}") from error
    # Implementations raise the errors of their own clients.
    except Exception as error:
        if check:
            raise ConfigReadError(f"cannot read configuration center {url}") from error
        _logger.warning("Starting without configuration center %s", url, exc_info=True)
        return {}

    if text is None or not text.strip():
        return {}

    try:
        data = parser.loads(text)
    except ConfigParseError as error:
        raise ConfigParseError(f"{error} in {key!r} of group {group!r}") from error.__cause__
    # The configuration center is already connected and cannot move itself.
    if "config_center" in data:
        raise ConfigError(f"configuration center entry {key!r} must not set config_center")
    return data


def _parser(source: str, format: str | None) -> ConfigParser:
    """Return the parser ``format`` names, else the one the suffix of ``source``, a path or key, names."""
    name = format or PurePosixPath(source).suffix.removeprefix(".")
    if not name:
        raise ConfigReadError(f"cannot select a parser for {source!r}: it has no suffix and no format is set")

    try:
        return get_parser(name)
    except ConfigReadError as error:
        raise ConfigReadError(f"{error} for {source!r}") from error.__cause__


def _read_prefixed_env(prefix: str) -> ConfigData:
    """Read the environment variables named with ``prefix`` as nested, lowercase keys.

    ``__`` separates path segments: DUBBO__PROTOCOLS__TRI__PORT sets
    ``protocols.tri.port``. A variable that targets a mapping, list or nested
    configuration holds JSON, which keeps keys such as dotted service names
    intact. Other values stay strings until the configuration converts them.

    Raises:
        ConfigReadError: Two variables collide after normalization, a path has
            an empty segment, or a JSON value is invalid.
    """
    tree: dict[str, object] = {}
    for name, value in os.environ.items():
        if not name.startswith(prefix):
            continue
        try:
            insert_path(tree, name[len(prefix) :].lower().split("__"), value)
        except ValueError as error:
            raise ConfigReadError(f"invalid configuration path in environment variable {name!r}: {error}") from None

    try:
        return decode_json(tree, DubboConfig)
    except ValueError as error:
        raise ConfigReadError(f"invalid environment configuration: {error}") from error.__cause__
