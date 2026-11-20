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
import time
import typing
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

from dubbo.constants import DEFAULT_WARMUP, DEFAULT_WEIGHT, TIMESTAMP_KEY, WARMUP_KEY, WEIGHT_KEY
from dubbo.extension import extension_point
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL
from dubbo.utils.converters import milliseconds

__all__ = ["LoadBalance", "PerSequence", "Weights"]

_logger = logging.getLogger(__name__)

# The sequences of invokers kept for each method.
_SEQUENCES = 4

T = TypeVar("T")


# The weight a provider sets for a method, when it registered in seconds since the epoch, and its warmup in seconds.
_Settings = tuple[int, float, float]


@extension_point("apache_dubbo.loadbalance")
class LoadBalance(typing.Protocol):
    """Chooses the provider an attempt of a call goes to.

    Implement ``__init__(url)`` and ``select``, and install the class under
    the entry point group ``apache_dubbo.loadbalance``; ``loadbalance`` and
    ``{method}.loadbalance`` name it, ``random`` by default. A cluster
    creates one with the URL of the reference, and one more for each method
    that names its own, and calls ``select`` on every attempt, in the event
    loop, for many calls at once. ``invokers`` stays the same object while
    the providers and their routes do not change, so what is derived from
    it may be kept by identity, as `PerSequence` keeps it. It holds nothing
    and is never closed.
    """

    def __init__(self, url: URL) -> None: ...

    def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        """Return one of ``invokers``, which holds at least one, for ``invocation``; it neither blocks nor raises."""
        ...


class PerSequence(Generic[T]):
    """What a load balance derives from each sequence of invokers it chooses among, for a method, for the last few used.

    Routing can offer the invokers of each call as one of a few sequences,
    each the same object while the providers do not change, so one is kept
    for each of the last 4 sequences used with a method. A sequence is told
    apart by identity and held while kept, so that its id is not reused.
    """

    def __init__(self, derive: Callable[[Sequence[Invoker], str], T]) -> None:
        """``derive`` returns what to keep for a sequence and a method."""
        self._derive = derive
        # By method, then by the id of the sequence, the least recently used first: the sequence and what it gave.
        self._kept: dict[str, dict[int, tuple[Sequence[Invoker], T]]] = {}

    def get(self, invokers: Sequence[Invoker], method: str) -> T:
        """Return what is kept for ``invokers`` and ``method``, derived on first use."""
        kept = self._kept.get(method)
        if kept is None:
            kept = self._kept[method] = {}

        key = id(invokers)
        entry = kept.pop(key, None)
        if entry is None:
            if len(kept) >= _SEQUENCES:
                del kept[next(iter(kept))]
            entry = (invokers, self._derive(invokers, method))
        kept[key] = entry
        return entry[1]


class Weights:
    """The weights of the providers a load balance chooses among, for each method.

    The weight of a provider for a method is the parameter ``{method}.weight``
    of its URL, else ``weight``, else 100; an invalid one counts as 100. A
    provider that registered, by its ``timestamp``, less than ``warmup`` ago,
    10 minutes by default, weighs in proportion to the time since, and at
    least 1. The settings are read once for each sequence of invokers a
    `PerSequence` keeps; the weights, too, and while one warms up; until
    then the same list is returned.
    """

    def __init__(self) -> None:
        self._weighed = PerSequence(_weighed)

    def get(self, invokers: Sequence[Invoker], method: str) -> list[int]:
        """Return the weight of each of ``invokers`` for ``method``, in order."""
        return self._weighed.get(invokers, method).weights()


class _Weighed:
    """The weights of one sequence of providers for a method, from the settings each of them sets."""

    def __init__(self, settings: list[_Settings]) -> None:
        self._settings = settings
        # None while one warms up.
        self._weights: list[int] | None = None

    def weights(self) -> list[int]:
        if self._weights is not None:
            return self._weights

        now = time.time()
        computed = [_weight(settings, now) for settings in self._settings]
        weights = [weight for weight, _ in computed]
        if not any(warming for _, warming in computed):
            self._weights = weights
        return weights


def _weighed(invokers: Sequence[Invoker], method: str) -> _Weighed:
    return _Weighed([_settings(invoker.url, method) for invoker in invokers])


def _settings(url: URL, method: str) -> _Settings:
    """Return the weight, registration time and warmup the provider at ``url`` sets for ``method``."""
    try:
        default = url.get_parameter(WEIGHT_KEY, int, DEFAULT_WEIGHT)
        weight = max(url.get_parameter(f"{method}.{WEIGHT_KEY}", int, default), 0)
        registered = url.get_parameter(TIMESTAMP_KEY, int, 0) / 1000
        warmup = url.get_parameter(WARMUP_KEY, milliseconds, DEFAULT_WARMUP)
    except ValueError:
        _logger.warning("Provider %s has an invalid weight, timestamp or warmup; it weighs %d", url, DEFAULT_WEIGHT)
        return DEFAULT_WEIGHT, 0, 0

    return weight, registered, warmup


def _weight(settings: _Settings, now: float) -> tuple[int, bool]:
    """Return the weight of a provider with ``settings`` at ``now``, and whether it still warms up."""
    weight, registered, warmup = settings
    uptime = now - registered
    if weight == 0 or registered <= 0 or warmup == 0 or uptime >= warmup:
        return weight, False
    # A clock behind that of the provider counts it as just registered.
    return max(1, min(weight, int(max(uptime, 0) / warmup * weight))), True
