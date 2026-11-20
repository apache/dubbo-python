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

import time
from typing import cast

from dubbo.constants import DEFAULT_TPS_INTERVAL, TPS_INTERVAL_KEY, TPS_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL
from dubbo.utils.converters import milliseconds

from .base import Filter

__all__ = ["TpsFilter"]


# The protocol, host, port and path of a service URL, and the method counted alone or None for the others.
_Key = tuple[str, str | None, int | None, str, str | None]


class TpsWindows:
    """The windows in which an application counts the calls of the services it serves.

    A window is kept for each URL a service is served with, told apart by
    its protocol, host, port and path, and each method counted alone or
    ``None`` for the others. It outlives the filters that the override
    rules create again, so that the calls a window has counted stay
    counted.
    """

    def __init__(self) -> None:
        self._windows: dict[_Key, _Window] = {}

    def get(self, url: URL, method: str | None) -> "_Window":
        """Return the window of ``method`` of the service ``url``, a new one on first use."""
        key = url.protocol, url.host, url.port, url.path, method
        window = self._windows.get(key)
        if window is None:
            window = self._windows[key] = _Window()
        return window


class TpsFilter(Filter):
    """Fails with ``UNAVAILABLE`` the calls beyond those the service ``url`` may serve in each window.

    The methods are counted together: ``tps`` calls in each window of
    ``tps.interval``. A method that sets ``{method}.tps`` is counted on its
    own instead, in windows of ``{method}.tps.interval``, else
    ``tps.interval``. A rate of 0 or less means no limit. The windows are
    those of the ``TpsWindows`` of the application: a changed rate applies to
    the calls the current window has counted, and a changed interval from the
    next window.

    Raises:
        RuntimeError: No application made ``url``.
    """

    def __init__(self, url: URL) -> None:
        windows = _windows(url)
        interval = url.get_parameter(TPS_INTERVAL_KEY, milliseconds, DEFAULT_TPS_INTERVAL)
        intervals = url.get_method_parameters(TPS_INTERVAL_KEY, milliseconds)
        self._shared = _limit(windows.get(url, None), url.get_parameter(TPS_KEY, int, 0), interval)
        self._limits = {
            method: _limit(windows.get(url, method), rate, intervals.get(method, interval))
            for method, rate in url.get_method_parameters(TPS_KEY, int).items()
        }

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        limit = self._limits.get(invocation.method, self._shared)
        if limit is not None and not limit.take():
            error = RpcError(
                Status.UNAVAILABLE,
                f"{invocation.interface}.{invocation.method} serves {limit.rate} calls in {limit.interval} seconds",
            )
            return Result(error=error)

        return await call_next(invocation)


class _Window:
    """The calls counted in a window, which ends at ``end`` on the monotonic clock."""

    def __init__(self) -> None:
        self.end = float("-inf")
        self.taken = 0


class _Limit:
    """Admits ``rate`` calls in fixed windows of ``interval`` seconds, the first starting with the first call."""

    def __init__(self, window: _Window, rate: int, interval: float) -> None:
        self.rate = rate
        self.interval = interval
        self._window = window

    def take(self) -> bool:
        """Count one call; return whether the window has room for it."""
        window = self._window
        now = time.monotonic()
        if now >= window.end:
            window.end = now + self.interval
            window.taken = 0
        if window.taken >= self.rate:
            return False

        window.taken += 1
        return True


def _windows(url: URL) -> TpsWindows:
    return cast(TpsWindows, url.scope.state.setdefault(TpsWindows, TpsWindows()))


def _limit(window: _Window, rate: int, interval: float) -> _Limit | None:
    return _Limit(window, rate, interval) if rate > 0 else None
