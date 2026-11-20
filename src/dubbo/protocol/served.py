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

"""What the Dubbo and Triple protocols share: the servers they open and the services each serves, the clients their invokers share, and the calls the invokers make."""

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from contextlib import AsyncExitStack
from typing import Any, Generic, Protocol, TypeVar

import anyio
import attrs

from dubbo.constants import DEFAULT_TIMEOUT, TIMEOUT_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.extension import Resource
from dubbo.rpc.invocation import Invoker, Result
from dubbo.url import URL, service_key
from dubbo.utils import wait_then_cancel
from dubbo.utils.converters import milliseconds

from .base import Exporter

__all__ = ["Calls", "ClientPool", "ServedExporter", "ServedService", "Servers", "call_within", "method_timeout"]


@attrs.define(eq=False, kw_only=True)
class ServedService:
    """A service exported on a server, which tracks the tasks of its running calls so that closing can end them."""

    interface: str
    group: str
    version: str
    invoker: Invoker
    _calls: set[asyncio.Task[Any]] = attrs.field(factory=set, init=False)

    @property
    def key(self) -> str:
        """The Dubbo key of the service: ``group/interface:version``, leaving out an empty group or version."""
        return service_key(self.interface, self.group, self.version)

    def track(self, task: asyncio.Task[Any]) -> None:
        """Track ``task``, which serves a call, as a running call until it finishes."""
        self._calls.add(task)
        task.add_done_callback(self._calls.discard)

    async def drain(self, grace: float) -> None:
        """Wait up to ``grace`` seconds for the running calls, once no new ones can start, then cancel the rest."""
        await wait_then_cancel(self._calls, grace)


class _Server(Resource, Protocol):
    """What the services exported on one address share: a server that listens there while it is open."""

    # Seconds an unexported service waits for its running calls before they are cancelled.
    shutwait: float

    @property
    def address(self) -> tuple[str, int]:
        """The host and the port the server listens on."""
        ...

    def check(self, url: URL) -> None:
        """Check that ``url`` asks for the settings the server runs with.

        Raises:
            ValueError: A setting differs.
        """
        ...

    def remove(self, service: ServedService) -> None:
        """Stop serving ``service``; its new calls fail so that callers retry with another provider."""
        ...

    def announce_shutdown(self) -> None:
        """Tell the callers that the server stops taking calls, while serving on."""
        ...


@attrs.define(kw_only=True, eq=False)
class ServedExporter(Exporter):
    """A service exported on a server.

    Closing it removes the service from the server, whose new calls then
    fail so that callers retry with another provider, waits for its running
    calls as long as the server's ``shutwait``, and then cancels the rest.
    """

    server: _Server
    service: ServedService
    _url: URL = attrs.field(alias="url")
    _closed: bool = attrs.field(default=False, init=False)

    @property
    def url(self) -> URL:
        return self._url

    async def aclose(self) -> None:
        if self._closed:
            return

        self._closed = True
        self.server.remove(self.service)
        await self.service.drain(self.server.shutwait)


_S = TypeVar("_S", bound=_Server)


class Servers(Resource, Generic[_S]):
    """The servers a protocol opens, one for each address; closing closes them all."""

    def __init__(self) -> None:
        self._servers: dict[tuple[str, int], _S] = {}
        self._stack = AsyncExitStack()
        self._lock = anyio.Lock()

    async def serve(self, url: URL, create: Callable[[], _S], add: Callable[[_S], None]) -> _S:
        """Return the server for the address of ``url``, once ``add`` has added a service to it.

        The first service on an address enters the server ``create`` makes,
        which closes again should ``add`` fail. A later one shares that
        server, whose settings ``url`` must ask for.

        Raises:
            ValueError: The URL has no host, or asks for other settings than
                the server on its address runs with.
            Exception: What ``create``, entering the server or ``add`` raises.
        """
        host = url.host
        if host is None:
            raise ValueError(f"a server needs a host to listen on: {url}")

        address = (host, url.port or 0)
        async with self._lock:
            server = self._servers.get(address)
            if server is not None:
                server.check(url)
                add(server)
                return server

            async with AsyncExitStack() as opening:
                server = await opening.enter_async_context(create())
                add(server)
                self._stack.push_async_exit(opening.pop_all())
            # A server on port 0 is also found under the port it was given.
            self._servers[address] = self._servers[(host, server.address[1])] = server
            return server

    def announce_shutdown(self) -> None:
        for server in set(self._servers.values()):
            server.announce_shutdown()

    async def aclose(self) -> None:
        # The lock is held only while an export opens its server, so that a cancelled close still closes.
        with anyio.CancelScope(shield=True):
            await self._lock.acquire()
        try:
            self._servers = {}
            await self._stack.aclose()
        finally:
            self._lock.release()


_C = TypeVar("_C", bound=Resource)


class ClientPool(Resource, Generic[_C]):
    """The clients that the invokers of one protocol share, one for each key.

    Each `acquire` takes a share in the client of a key, opening it on first
    use, and each share goes back with `release`; the last one closes the
    client. Closing the pool closes the clients still shared. Clients hold no
    task's cancel scope, so any task may acquire and release them.
    """

    def __init__(self) -> None:
        self._shares: dict[Hashable, _Share[_C]] = {}
        # The key of each client, by the client's id.
        self._keys: dict[int, Hashable] = {}
        self._closed = False

    async def acquire(self, key: Hashable, create: Callable[[], _C]) -> _C:
        """Take a share in the client of ``key``, which the first share creates with ``create`` and enters.

        Raises:
            RuntimeError: The pool is closed.
            Exception: What ``create`` or entering the client raises.
        """
        if self._closed:
            raise RuntimeError("the client pool is closed")

        share = self._shares.get(key)
        if share is not None:
            share.shares += 1
            return share.client

        client = await create().__aenter__()
        if self._closed:
            await client.aclose()
            raise RuntimeError("the client pool is closed")

        share = self._shares.get(key)
        if share is None:
            self._shares[key] = _Share(client=client, shares=1)
            self._keys[id(client)] = key
            return client

        # Another invoker created the client meanwhile; its share is taken before this one closes.
        share.shares += 1
        try:
            await client.aclose()
        except BaseException:
            await self.release(share.client)
            raise
        return share.client

    async def release(self, client: _C) -> None:
        """Give back a share in ``client``, closing it when no share is left.

        Releasing a client the pool no longer holds does nothing.
        """
        key = self._keys.get(id(client))
        if key is None:
            return

        share = self._shares[key]
        share.shares -= 1
        if share.shares:
            return

        del self._shares[key], self._keys[id(client)]
        await client.aclose()

    async def aclose(self) -> None:
        """Close every client still shared, each even if closing another raises or is cancelled."""
        self._closed = True
        shares = list(self._shares.values())
        self._shares.clear()
        self._keys.clear()

        async with AsyncExitStack() as stack:
            for share in shares:
                stack.push_async_callback(share.client.aclose)


class Calls:
    """The number of calls an invoker is making, which closing waits for."""

    def __init__(self) -> None:
        self._count = 0
        self._idle: anyio.Event | None = None

    def enter(self) -> None:
        """Count a call that starts."""
        self._count += 1

    def leave(self) -> None:
        """Count a call that ends."""
        self._count -= 1
        if not self._count and self._idle is not None:
            self._idle.set()

    async def drain(self, grace: float) -> None:
        """Wait up to ``grace`` seconds for the calls under way to end."""
        if self._count:
            self._idle = anyio.Event()
            with anyio.move_on_after(grace):
                await self._idle.wait()


@attrs.define(kw_only=True, eq=False)
class _Share(Generic[_C]):
    client: _C
    shares: int


async def call_within(timeout: float, method: str, call: Awaitable[Result]) -> Result:
    """Return the result of ``call``, a call of ``method``, or one of ``DEADLINE_EXCEEDED`` once it has run ``timeout`` seconds."""
    # An asyncio timeout: a call runs 11% faster over Dubbo and 23% over Triple than in an AnyIO cancel
    # scope, measured at 64 at once.
    deadline = asyncio.timeout(timeout)
    try:
        async with deadline:
            return await call
    except TimeoutError:
        if not deadline.expired():
            raise

    return Result(error=RpcError(Status.DEADLINE_EXCEEDED, f"{method} did not complete within {timeout} seconds"))


def method_timeout(url: URL, method: str) -> float:
    """Return the seconds a unary call of ``method`` may take: the milliseconds of ``{method}.timeout``, else of ``timeout``; one second when both are absent.

    Raises:
        ValueError: A timeout is no whole number of milliseconds.
    """
    default = url.get_parameter(TIMEOUT_KEY, milliseconds, DEFAULT_TIMEOUT)
    return url.get_parameter(f"{method}.{TIMEOUT_KEY}", milliseconds, default)
