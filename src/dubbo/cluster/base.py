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
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AsyncExitStack

from dubbo.constants import (
    CLUSTER_KEY,
    DEFAULT_CLUSTER,
    DEFAULT_LOADBALANCE,
    DEFAULT_STICKY,
    LOADBALANCE_KEY,
    STICKY_KEY,
)
from dubbo.exceptions import RpcError, Status
from dubbo.extension import extension_point, extensions
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL
from dubbo.utils.converters import boolean

from .directory import Directory
from .loadbalance import LoadBalance

__all__ = ["BaseCluster", "Cluster", "available_invokers", "create_cluster"]


@extension_point("apache_dubbo.cluster")
class Cluster(Invoker, typing.Protocol):
    """Makes each call of a reference through its providers: which it tries, how often, and what a failure returns.

    Implement the `Invoker` contract with ``__init__(url, directory)``, or
    subclass `BaseCluster`, and install the class under the entry point
    group ``apache_dubbo.cluster``; the ``cluster`` parameter of the
    reference names it, ``failover`` by default.

    `create_cluster` creates one with the URL of the reference, whose
    parameters, such as ``loadbalance`` and ``retries``, configure it, and
    the directory it asks for candidates on every attempt, and enters it
    before its first call. It owns the directory: closing the cluster
    closes it. It is an invoker over the invokers of the directory, so a
    directory may hold clusters too, and it is available while the
    directory is.

    ``invoke`` runs in the event loop, for many calls at once, and returns
    a failure in `Result.error`. A call that finds no invoker in the
    directory ends with ``UNAVAILABLE``; otherwise each attempt chooses
    among the available invokers, or among all of them when none is,
    asking the one it chooses first and the others only when that one is
    not available.
    """

    def __init__(self, url: URL, directory: Directory) -> None: ...


class BaseCluster(Cluster, ABC):
    """The part of a cluster every strategy shares; a strategy implements `_invoke`.

    A call that the directory has no invoker for ends with ``UNAVAILABLE``
    before the strategy sees it.

    Each attempt chooses its invoker with the load balance of the method
    called: the one ``{method}.loadbalance`` names, else the one
    ``loadbalance`` names, else ``random``. With ``{method}.sticky``, else
    ``sticky``, true, it chooses the invoker it chose last again while that
    one is among the candidates and available.

    Attributes:
        directory: Where the invokers of each attempt come from.
    """

    def __init__(self, url: URL, directory: Directory) -> None:
        super().__init__(url, directory)

        self._url = url
        self.directory = directory
        self._load_balance = _load_balance(url.parameters.get(LOADBALANCE_KEY, DEFAULT_LOADBALANCE), url)
        self._load_balances = {
            method: _load_balance(name, url) for method, name in url.get_method_parameters(LOADBALANCE_KEY, str).items()
        }
        self._sticky = url.get_parameter(STICKY_KEY, boolean, DEFAULT_STICKY)
        self._stickies = url.get_method_parameters(STICKY_KEY, boolean)
        self._last: Invoker | None = None

    @property
    def url(self) -> URL:
        return self._url

    @property
    def available(self) -> bool:
        return self.directory.available

    async def invoke(self, invocation: Invocation) -> Result:
        invokers = self.directory.candidates(invocation)
        if not invokers:
            return Result(error=RpcError(Status.UNAVAILABLE, f"no provider of {invocation.interface} is available"))

        return await self._invoke(invocation, invokers)

    async def aclose(self) -> None:
        await self.directory.aclose()

    def _select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        """Return the invoker of an attempt of ``invocation`` among ``invokers``, as the load balance of its method chooses.

        One chosen while unavailable is chosen again among the available
        ones, if any, so that an attempt asks one invoker whether it is
        available while all are.
        """
        sticky = self._stickies.get(invocation.method, self._sticky)
        last = self._last
        if sticky and last is not None and last in invokers and last.available:
            return last

        load_balance = self._load_balances.get(invocation.method, self._load_balance)
        chosen = load_balance.select(invokers, invocation)
        if not chosen.available:
            available = available_invokers(invokers)
            if available is not invokers:
                chosen = load_balance.select(available, invocation)

        if sticky:
            self._last = chosen
        return chosen

    @abstractmethod
    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        """Make the call through ``invokers``, which holds at least one, and return how it ended."""


def available_invokers(invokers: Sequence[Invoker]) -> Sequence[Invoker]:
    """Return those of ``invokers`` that are available, ``invokers`` itself when all or none are."""
    available = [invoker for invoker in invokers if invoker.available]
    return invokers if len(available) == len(invokers) or not available else available


async def create_cluster(url: URL, directory: Directory) -> Cluster:
    """Open ``directory`` and return the cluster the ``cluster`` parameter of ``url`` names over it, ``failover`` when absent.

    The cluster is entered, and owns ``directory`` from the call on: closing
    the cluster closes it, and so does a failure to create or enter the
    cluster.

    Raises:
        ExtensionError: No implementation has that name.
    """
    async with AsyncExitStack() as stack:
        stack.push_async_callback(directory.aclose)
        await directory.__aenter__()
        cluster = extensions.get(Cluster, url.parameters.get(CLUSTER_KEY, DEFAULT_CLUSTER))(url, directory)
        await cluster.__aenter__()
        stack.pop_all()

    return cluster


def _load_balance(name: str, url: URL) -> LoadBalance:
    return extensions.get(LoadBalance, name)(url)
