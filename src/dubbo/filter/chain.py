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

"""Building the filter chains of services and of calls to providers."""

import functools
from collections.abc import Callable, Sequence

from dubbo.constants import (
    ACCESSLOG_KEY,
    ACTIVES_KEY,
    DEPRECATED_KEY,
    EXECUTES_KEY,
    LEAST_ACTIVE_LOADBALANCE,
    LOADBALANCE_KEY,
    SERVICE_FILTER_KEY,
    TOKEN_KEY,
    TPS_KEY,
)
from dubbo.rpc.invocation import Invocation, Invoke, Invoker, Result
from dubbo.url import URL
from dubbo.utils.converters import boolean, comma_separated, is_true

from .accesslog import AccessLogFilter
from .activecount import ActiveCountFilter
from .actives import ActivesFilter
from .base import ATTEMPT_FILTER_KEY, Filter, get_filters
from .deprecated import DeprecatedFilter
from .executes import ExecutesFilter
from .token import TokenFilter
from .tps import TpsFilter

__all__ = ["chain_filters", "get_attempt_filters", "get_service_filters"]

# Filters that settings add, the first outermost: each with the parameter that adds it when its value, or that of
# some method, converts to a true value.
_Added = tuple[tuple[str, Callable[[str], object], Callable[[URL], Filter]], ...]


def get_service_filters(url: URL) -> list[Filter]:
    """Return the filters each call to the service ``url`` runs through, the first outermost.

    First come those its settings add: ``accesslog`` logs each call,
    ``token`` refuses those without it, and ``tps`` and ``executes`` limit
    them; then those ``service.filter`` names.
    """
    added = _added(
        (
            (ACCESSLOG_KEY, boolean, AccessLogFilter),
            (TOKEN_KEY, str, TokenFilter),
            (TPS_KEY, int, TpsFilter),
            (EXECUTES_KEY, int, ExecutesFilter),
        ),
        url,
    )
    return added + get_filters(url.get_parameter(SERVICE_FILTER_KEY, comma_separated, ()), url)


def get_attempt_filters(url: URL) -> list[Filter]:
    """Return the filters each attempt of a call on the provider ``url`` runs through, the first outermost.

    First come those its settings add: ``deprecated`` warns of the methods
    the provider deprecates, ``actives`` limits the calls made to it at
    once, and the ``leastactive`` load balance counts those under way,
    which ``actives`` counts too; then those ``reference.attempt-filter``
    names.
    """
    added = _added(
        (
            (DEPRECATED_KEY, is_true, DeprecatedFilter),
            (ACTIVES_KEY, int, ActivesFilter),
            (LOADBALANCE_KEY, lambda name: name == LEAST_ACTIVE_LOADBALANCE, ActiveCountFilter),
        ),
        url,
    )
    # ActivesFilter counts the calls under way itself.
    if any(isinstance(filter_, ActivesFilter) for filter_ in added):
        added = [filter_ for filter_ in added if not isinstance(filter_, ActiveCountFilter)]

    return added + get_filters(url.get_parameter(ATTEMPT_FILTER_KEY, comma_separated, ()), url)


def chain_filters(invoker: Invoker, filters: Sequence[Filter]) -> Invoker:
    """Return an invoker that makes the calls of ``invoker`` through ``filters``, the first outermost.

    It has the URL and the availability of ``invoker``, and closing it closes ``invoker``.
    """
    if not filters:
        return invoker

    return _Chained(invoker, filters)


class _Chained(Invoker):
    """Makes the calls of an invoker through filters, and is that invoker otherwise."""

    def __init__(self, invoker: Invoker, filters: Sequence[Filter]) -> None:
        call_next: Invoke = invoker.invoke
        for filter_ in reversed(filters):
            call_next = functools.partial(filter_.invoke, call_next)
        self._invoker = invoker
        self._call = call_next

    @property
    def url(self) -> URL:
        return self._invoker.url

    @property
    def available(self) -> bool:
        return self._invoker.available

    async def invoke(self, invocation: Invocation) -> Result:
        return await self._call(invocation)

    async def aclose(self) -> None:
        await self._invoker.aclose()


def _added(table: _Added, url: URL) -> list[Filter]:
    return [
        create(url)
        for key, convert, create in table
        if url.get_parameter(key, convert, None) or any(url.get_method_parameters(key, convert).values())
    ]
