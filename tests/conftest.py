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

"""Fixtures shared by the tests."""

import asyncio
import gc
import math
import selectors
import sys
import threading
import typing
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Self

import anyio
import attrs
import pytest

from dubbo.config_center import ConfigCenter
from dubbo.extension import extensions
from dubbo.transport.zookeeper import ZookeeperClient
from dubbo.url import URL
from dubbo.utils import Latest

_H2_REQUEST_HEADERS = (
    (b":method", b"POST"),
    (b":scheme", b"http"),
    (b":authority", b"127.0.0.1"),
    (b":path", b"/test"),
    (b"content-type", b"application/grpc"),
)


_H2_RESPONSE_HEADERS = (
    (b":status", b"200"),
    (b"content-type", b"application/grpc"),
)


def _h2_url(host: str, port: int, **parameters: str) -> URL:
    """Return an H2 URL; underscores in parameter names stand for hyphens."""
    return URL(
        protocol="tri",
        host=host,
        port=port,
        parameters={name.replace("_", "-"): value for name, value in parameters.items()},
    )


class Ensemble:
    """The nodes of a ZooKeeper ensemble held in memory, shared by the clients created with ``client=memory``."""

    def __init__(self) -> None:
        self.nodes: dict[str, bytes] = {"/": b""}
        self.owners: dict[str, object] = {}
        self.urls: list[URL] = []
        self.changed = anyio.Event()

    def touch(self) -> None:
        self.changed.set()
        self.changed = anyio.Event()

    def put(self, path: str, data: bytes, owner: object | None = None) -> None:
        parts = path.strip("/").split("/")
        for depth in range(1, len(parts)):
            self.nodes.setdefault("/" + "/".join(parts[:depth]), b"")
        self.nodes[path] = data
        if owner is None:
            self.owners.pop(path, None)
        else:
            self.owners[path] = owner
        self.touch()

    def remove(self, path: str) -> None:
        if self.nodes.pop(path, None) is not None:
            self.owners.pop(path, None)
            self.touch()

    def children(self, path: str) -> list[str] | None:
        if path not in self.nodes:
            return None
        prefix = path.rstrip("/") + "/"
        return sorted(
            node[len(prefix) :] for node in self.nodes if node.startswith(prefix) and "/" not in node[len(prefix) :]
        )

    def close(self, owner: object) -> None:
        for path in [path for path, holder in self.owners.items() if holder is owner]:
            self.remove(path)


def memory_client(ensemble: Ensemble) -> Callable[[URL], ZookeeperClient]:
    class MemoryClient(ZookeeperClient):
        def __init__(self, url: URL) -> None:
            super().__init__(url)
            ensemble.urls.append(url)
            # The keeper of each ephemeral node this client keeps.
            self._keepers: dict[str, object] = {}

        async def __aenter__(self) -> Self:
            return self

        async def aclose(self) -> None:
            ensemble.close(self)

        async def get(self, path: str) -> bytes | None:
            return ensemble.nodes.get(path)

        @asynccontextmanager
        async def keep_ephemeral(self, path: str, data: bytes = b"") -> AsyncIterator[None]:
            keeper = self._keepers[path] = object()
            ensemble.put(path, data, self)
            try:
                yield
            finally:
                if self._keepers.get(path) is keeper:
                    del self._keepers[path]
                    ensemble.remove(path)

        async def update(self, path: str, change: Callable[[bytes | None], bytes]) -> None:
            current = ensemble.nodes.get(path)
            changed = change(current)
            if changed != current:
                ensemble.put(path, changed)

        @asynccontextmanager
        async def watch(self, path: str) -> AsyncIterator[AsyncIterator[bytes | None]]:
            yield self._follow(lambda: ensemble.nodes.get(path))

        @asynccontextmanager
        async def watch_children(self, path: str) -> AsyncIterator[AsyncIterator[list[str]]]:
            yield self._follow(lambda: ensemble.children(path) or [])

        # The node operations that only tests use, which the integration NodesClient has too.

        async def children(self, path: str) -> list[str]:
            return ensemble.children(path) or []

        async def create(self, path: str, data: bytes = b"") -> None:
            if path not in ensemble.nodes:
                ensemble.put(path, data)

        async def set(self, path: str, data: bytes) -> None:
            ensemble.put(path, data)

        async def delete(self, path: str) -> None:
            ensemble.remove(path)

        async def _follow(self, read: Callable[[], object]) -> AsyncIterator[typing.Any]:
            last: object = object()
            while True:
                changed = ensemble.changed
                value = read()
                if value != last:
                    last = value
                    yield value
                await changed.wait()

    return MemoryClient


@attrs.define
class ConfigStore:
    """The entries by group and key of the configuration center ``memory``, the centers created for it and the reads they served.

    A watch sees each entry that `put` changes; ``error``, when set, fails every read.
    """

    entries: dict[tuple[str, str], str] = attrs.field(factory=dict)
    centers: list["MemoryConfigCenter"] = attrs.field(factory=list)
    reads: list[tuple[str, str]] = attrs.field(factory=list)
    error: Exception | None = None
    _latest: dict[tuple[str, str], Latest[str | None]] = attrs.field(factory=dict)

    def put(self, key: str, text: str | None, *, group: str = "dubbo") -> None:
        if text is None:
            self.entries.pop((group, key), None)
        else:
            self.entries[group, key] = text
        self.watched(group, key).publish(text)

    def watched(self, group: str, key: str) -> Latest[str | None]:
        latest = self._latest.get((group, key))
        if latest is None:
            latest = self._latest[group, key] = Latest()
            latest.publish(self.entries.get((group, key)))
        return latest

    def create(self, url: URL) -> "MemoryConfigCenter":
        center = MemoryConfigCenter(self, url)
        self.centers.append(center)
        return center


@attrs.define
class MemoryConfigCenter(ConfigCenter):
    store: ConfigStore
    url: URL
    connected: bool = False
    closed: bool = False

    async def __aenter__(self) -> Self:
        self.connected = True
        return self

    async def aclose(self) -> None:
        self.closed = True

    async def get(self, key: str, *, group: str) -> str | None:
        if self.store.error is not None:
            raise self.store.error
        self.store.reads.append((group, key))
        return self.store.entries.get((group, key))

    @asynccontextmanager
    async def watch(self, key: str, *, group: str) -> AsyncIterator[AsyncIterator[str | None]]:
        yield aiter(self.store.watched(group, key))


# Real time an idle event loop waits for I/O before its clock jumps, so that bytes between its sockets arrive first.
_SETTLE = 0.005

_Poller = asyncio.IocpProactor if sys.platform == "win32" else selectors.DefaultSelector  # ty: ignore[unresolved-attribute]
_Loop = asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.SelectorEventLoop  # ty: ignore[unresolved-attribute]


class _JumpingPoller(_Poller):
    """Waits for I/O, and moves its clock to the next timer of its loop when none comes and no thread works for it."""

    def __init__(self, working: Callable[[], bool]) -> None:
        super().__init__()
        self.now = 0.0
        self._working = working

    def select(self, timeout: float | None = None) -> typing.Any:
        # Without a timeout the loop waits for I/O alone; with a zero one it has callbacks ready.
        if not timeout:
            return super().select(timeout)
        events = super().select(min(timeout, _SETTLE))
        if not events and not self._working():
            self.now += timeout
        return events


class VirtualClockLoop(_Loop):
    """The default event loop of the platform, on a clock that starts at 0 and moves only while every task waits.

    A deadline then passes exactly when it is due, whatever the speed or clock of the host.
    """

    def __init__(self) -> None:
        self._poller = _JumpingPoller(self._working)
        super().__init__(self._poller)
        # Timers this close to due run at once; the resolution of the host's clock, 15.6 ms on Windows, would run them
        # early, while a jump lands on them to within a rounding.
        self._clock_resolution = 1e-9
        self._executing = 0
        # The threads of AnyIO, which the tests give the loop from inside a task.
        self.thread_limiter: anyio.CapacityLimiter | None = None

    def time(self) -> float:
        return self._poller.now

    def run_in_executor(self, executor: typing.Any, func: Callable[..., typing.Any], *args: typing.Any) -> typing.Any:
        future = super().run_in_executor(executor, func, *args)
        self._executing += 1
        future.add_done_callback(self._executed)
        return future

    def _executed(self, _: object) -> None:
        self._executing -= 1

    def _working(self) -> bool:
        return self._executing > 0 or (self.thread_limiter is not None and self.thread_limiter.borrowed_tokens > 0)


_AGAINST_SERVERS = ("zookeeper", "nacos")


@pytest.fixture
def anyio_backend(request: pytest.FixtureRequest) -> tuple[str, dict[str, typing.Any]]:
    """The virtual clock, except in a test that waits for a server, a thread or a process, which run in real time."""
    if any(request.node.get_closest_marker(marker) for marker in (*_AGAINST_SERVERS, "real_clock")):
        return "asyncio", {}
    return "asyncio", {"loop_factory": VirtualClockLoop}


@pytest.fixture(autouse=True)
async def _bound_runtime(anyio_backend: object, request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Fail a test instead of hanging when an asynchronous invariant breaks.

    A test against a real ZooKeeper or Nacos runs at the server's pace and bounds its own waits.

    After a test against Nacos, the channels of grpcio that it leaves are released before its event loop closes.
    The Nacos SDK calls through grpcio, which keeps one completion queue for the process while any of its channels
    lives, and a channel lives in a reference cycle until a collection. A queue that outlives the event loop of a
    test delivers to it the events of its calls once it is closed, in the event loop of a later test.
    """
    if any(request.node.get_closest_marker(marker) for marker in _AGAINST_SERVERS):
        yield
    else:
        with anyio.fail_after(10) as scope:
            # A test that keeps its event loop busy never moves the clock, so it fails after as long in real time.
            loop = asyncio.get_running_loop()
            if isinstance(loop, VirtualClockLoop):
                loop.thread_limiter = anyio.to_thread.current_default_thread_limiter()
            watchdog = threading.Timer(10, loop.call_soon_threadsafe, (setattr, scope, "deadline", -math.inf))
            watchdog.start()
            try:
                yield
            finally:
                watchdog.cancel()

    if request.node.get_closest_marker("nacos"):
        gc.collect()


@pytest.fixture
def request_headers():
    return _H2_REQUEST_HEADERS


@pytest.fixture
def response_headers():
    return _H2_RESPONSE_HEADERS


@pytest.fixture
def h2_url():
    return _h2_url


@pytest.fixture
def isolated_extensions(monkeypatch) -> None:
    """Start from a fresh view of the shared extensions so the test's registrations are undone."""
    monkeypatch.setattr(extensions, "_points", {})


@pytest.fixture
def memory_zookeeper(isolated_extensions) -> Ensemble:
    """An in-memory ensemble that URLs with ``client=memory`` connect to."""
    ensemble = Ensemble()
    extensions.register(ZookeeperClient, "memory", memory_client(ensemble))
    return ensemble


@pytest.fixture
def config_store(isolated_extensions) -> ConfigStore:
    """The configuration center ``memory``, registered on the shared extensions."""
    store = ConfigStore()
    extensions.register(ConfigCenter, "memory", store.create)
    return store
