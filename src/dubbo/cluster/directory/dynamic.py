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
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Self

import anyio
from anyio.abc import TaskGroup

from dubbo.constants import GROUP_KEY, VERSION_KEY
from dubbo.extension import ExtensionError
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import PROVIDER_URL, URL
from dubbo.utils import create_background_task_group, follow, release_shield

from ..router import Router, RouterChain
from .base import Directory

__all__ = ["DynamicDirectory", "Refer"]

_logger = logging.getLogger(__name__)


# Returns an invoker that calls the provider a URL names.
Refer = Callable[[URL], Awaitable[Invoker]]

# The protocol, host, port, path, group and version that tell providers apart.
_Identity = tuple[str, str | None, int | None, str, str, str]


class DynamicDirectory(Directory):
    """The invokers of the URLs ``subscribe()`` gives, each the URL to call a provider with, made by ``refer``.

    Providers are told apart by protocol, host, port, path, group and version;
    the first URL of each is called, and a provider whose URL, and the URL it
    published, ``PROVIDER_URL``, do not change keeps its invoker. Entering
    ``async with`` waits for the first URLs, and fails if they cannot be had.
    A subscription that fails or ends after them breaks its contract; that is
    logged, the invokers are kept, and it is subscribed again after a delay.

    It owns ``routers``, which act as one ``RouterChain``: they open before
    the first URLs, take each new set of invokers before calls see it, narrow
    the candidates of each call in turn, and close with it.
    """

    def __init__(
        self,
        subscribe: Callable[[], AbstractAsyncContextManager[AsyncIterator[list[URL]]]],
        refer: Refer,
        name: str,
        routers: Sequence[Router] = (),
    ) -> None:
        """``name`` tells, in logs, whose providers these are."""
        self._subscribe = subscribe
        self._refer = refer
        self._name = name
        self._chain = RouterChain(routers)
        self._invokers: dict[_Identity, Invoker] = {}
        # The URL each invoker was referred with, which a protocol may have filled in for the invoker's own.
        self._referred: dict[_Identity, URL] = {}
        self._choices: tuple[Invoker, ...] = ()
        self._stack = AsyncExitStack()
        # Set once entered; runs the subscription and the closing of gone providers.
        self._task_group: TaskGroup

    @property
    def available(self) -> bool:
        return any(invoker.available for invoker in self._choices)

    def candidates(self, invocation: Invocation) -> Sequence[Invoker]:
        return self._chain.route(self._choices, invocation)

    async def aclose(self) -> None:
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self._chain)
            stack.push_async_callback(self._close_invokers)
            task_group = self._task_group = await stack.enter_async_context(create_background_task_group())
            stack.callback(task_group.cancel_scope.cancel)
            await task_group.start(follow, self._subscribe, self._update, f"the providers of {self._name}")
            self._stack = stack.pop_all()

        return self

    async def _update(self, urls: list[URL]) -> None:
        """Refer the providers of ``urls`` that are new or changed, close those that are gone, and tell the routers."""
        wanted: dict[_Identity, URL] = {}
        for url in urls:
            wanted.setdefault(_identity(url), url)

        invokers: dict[_Identity, Invoker] = {}
        referred_with: dict[_Identity, URL] = {}
        referred: list[Invoker] = []
        try:
            for identity, url in wanted.items():
                invoker = self._invokers.get(identity)
                if invoker is None or _changed(self._referred[identity], url):
                    try:
                        invoker = await self._refer(url)
                    except (ExtensionError, OSError, TypeError, ValueError):
                        _logger.warning(
                            "Cannot call the provider %s of %s; leaving it out", url, self._name, exc_info=True
                        )
                        continue
                    referred.append(invoker)
                invokers[identity] = invoker
                referred_with[identity] = url
        except BaseException:
            # Invokers made for an update that does not happen belong to no one else; they have taken no calls.
            with release_shield():
                async with anyio.create_task_group() as task_group:
                    for invoker in referred:
                        task_group.start_soon(invoker.aclose)
            raise

        gone = [invoker for identity, invoker in self._invokers.items() if invokers.get(identity) is not invoker]
        self._invokers, self._referred = invokers, referred_with
        self._choices = tuple(invokers.values())
        # The invoker of a gone provider finishes its running calls without holding up the update.
        for invoker in gone:
            self._task_group.start_soon(invoker.aclose)
        self._chain.notify(self._choices)

    async def _close_invokers(self) -> None:
        invokers, self._invokers, self._referred, self._choices = self._invokers, {}, {}, ()
        try:
            self._chain.notify(self._choices)
        finally:
            async with anyio.create_task_group() as task_group:
                for invoker in invokers.values():
                    task_group.start_soon(invoker.aclose)


def _identity(url: URL) -> _Identity:
    parameters = url.parameters
    return url.protocol, url.host, url.port, url.path, parameters.get(GROUP_KEY, ""), parameters.get(VERSION_KEY, "")


def _changed(current: URL, url: URL) -> bool:
    return current != url or current.attributes.get(PROVIDER_URL) != url.attributes.get(PROVIDER_URL)
