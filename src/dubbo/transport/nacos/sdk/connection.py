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

"""What the naming and configuration clients of the SDK share: their settings, errors and disconnection."""

import logging
from collections.abc import Awaitable
from typing import TypeVar

from dubbo.constants import ACCESS_KEY_KEY, BACKUP_KEY, NAMESPACE_KEY, SECRET_KEY_KEY, TIMEOUT_KEY
from dubbo.url import URL
from dubbo.utils import release_scope, require_optional_dependency
from dubbo.utils.converters import comma_separated, milliseconds
from dubbo.utils.net import format_address, split_address

from ..exceptions import NacosError

with require_optional_dependency("v2.nacos", extra="nacos"):
    from v2.nacos import ClientConfig, NacosException

__all__ = ["call", "client_config", "release"]

T = TypeVar("T")

_logger = logging.getLogger(__name__)

_DEFAULT_PORT = 8848
_CLOSE_TIMEOUT = 10.0  # Seconds.


def client_config(url: URL) -> ClientConfig:
    """Return the settings of an SDK client of the connection ``url`` names.

    Raises:
        ValueError: ``timeout`` is not positive whole milliseconds.
    """
    parameters = url.parameters
    timeout = url.get_parameter(TIMEOUT_KEY, milliseconds, None)
    if timeout is not None and timeout <= 0:
        raise ValueError(f"URL parameter {TIMEOUT_KEY!r} must be positive")

    servers = [
        format_address(url.host or "", url.port or _DEFAULT_PORT),
        *map(_with_port, comma_separated(parameters.get(BACKUP_KEY, ""))),
    ]
    config = ClientConfig(
        server_addresses=",".join(servers),
        namespace_id=parameters.get(NAMESPACE_KEY, ""),
        username=url.username,
        password=url.password,
        access_key=parameters.get(ACCESS_KEY_KEY),
        secret_key=parameters.get(SECRET_KEY_KEY),
    )
    # Otherwise the SDK keeps the last instances of a service when none are left.
    config.update_cache_when_empty = True
    # The SDK reads its disk cache at start in a task that no one owns, and that leaves a file open when cut short.
    config.load_cache_at_start = False
    if timeout is not None:
        config.timeout_ms = config.grpc_config.grpc_timeout = round(timeout * 1000)
    return config


async def call(operation: Awaitable[T], action: str) -> T:
    """Return the result of the SDK ``operation``, raising its failure as a `NacosError` that names ``action``."""
    try:
        return await operation
    except NacosException as error:
        raise NacosError(f"cannot {action}: {error}") from error


async def release(operation: Awaitable[object], action: str) -> None:
    """Await ``operation``, which releases what the SDK holds, logging a failure.

    It waits at most ten seconds, or a moment once the caller is cancelled,
    as `dubbo.utils.release_scope` bounds it, then gives up.
    """
    with release_scope(_CLOSE_TIMEOUT):
        try:
            await operation
        except Exception:
            _logger.warning("Cannot %s", action, exc_info=True)


def _with_port(address: str) -> str:
    host, port = split_address(address)
    return format_address(host, port or _DEFAULT_PORT)
