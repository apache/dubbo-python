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

from collections.abc import Callable, Hashable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, Self, TypeVar, cast

import anyio
from anyio.abc import TaskGroup, TaskStatus

__all__ = ["ApplicationScope"]

T = TypeVar("T")


class ApplicationScope:
    """What the extensions of one application share: resources opened once and closed as it stops, and plain state.

    The application enters it before anything else and exits it after
    everything else; extensions reach it as ``url.scope``. It belongs to one
    event loop and is not thread-safe.

    `share` enters each resource in a task of the scope, so that, once handed
    to the request that opened it, the resource outlives that request's task
    and is not bound by its cancel scopes. Closing refuses new requests,
    waits for the resources still opening, then closes them in reverse order
    of opening; a cancelled close closes those still open at once.

    Attributes:
        state: Values the extensions share that open and close nothing, such
            as the counts of calls under way that ``actives`` limits and
            ``leastactive`` reads. An extension takes its entry on first use,
            under a key that is or starts with its own class, as in
            ``state.setdefault(ActiveCounts, ActiveCounts())``. Entries stay
            until the scope closes, so what one holds must drop by itself
            what no longer applies, as a count that falls to zero does.
    """

    def __init__(self) -> None:
        self.state: dict[Hashable, Any] = {}
        self._shared: dict[Hashable, object] = {}
        self._closers: list[tuple[anyio.Event, anyio.Event]] = []
        # Set as each resource that is opening has been handed to its request or has failed to open.
        self._opening: set[anyio.Event] = set()
        # One lock per key, so that a resource may share another while it opens.
        self._locks: dict[Hashable, anyio.Lock] = {}
        self._task_group: TaskGroup | None = None

    async def share(self, key: Hashable, factory: Callable[[], AbstractAsyncContextManager[T]]) -> T:
        """Return the resource shared under ``key``, entering ``factory()`` on the first request.

        Concurrent requests for ``key`` wait for the first; a failure to open
        is raised to it, and the next request tries again. Cancelling the
        request while the resource opens exits it. ``key`` is a tuple that
        starts with the implementation, then what tells its instances apart,
        as in ``(implementation, url)``. The caller never closes the resource.

        Raises:
            RuntimeError: The scope is not open, or is closing.
        """
        async with self._locks.setdefault(key, anyio.Lock()):
            if self._task_group is None:
                raise RuntimeError("the application scope is not open")
            if key not in self._shared:
                # Counted before its task runs, so that closing, which may begin meanwhile, waits for it.
                opened = anyio.Event()
                self._opening.add(opened)
                self._shared[key] = await self._task_group.start(self._hold, factory, opened)
                self._settle(opened)

        return cast(T, self._shared[key])

    async def __aenter__(self) -> Self:
        task_group = anyio.create_task_group()
        await task_group.__aenter__()
        self._task_group = task_group
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        task_group, self._task_group = self._task_group, None
        assert task_group is not None
        self._shared.clear()
        self.state.clear()

        try:
            while self._opening:
                await next(iter(self._opening)).wait()
            for close, closed in reversed(self._closers):
                close.set()
                await closed.wait()
        except BaseException:
            task_group.cancel_scope.cancel()
            for close, _ in self._closers:
                close.set()
            raise
        finally:
            await task_group.__aexit__(None, None, None)

    async def _hold(
        self,
        factory: Callable[[], AbstractAsyncContextManager[Any]],
        opened: anyio.Event,
        *,
        task_status: TaskStatus[Any],
    ) -> None:
        # Until its request has taken the resource, a cancellation of the request exits it; then it lives until
        # the scope closes it or its own cancel scopes end it, and exits under the cancellation, if any, that ends
        # the scope. The guard encloses the whole lifetime, so that it never stands between the resource and the
        # cancel scopes it entered.
        closed = anyio.Event()
        try:
            with anyio.CancelScope() as guard:
                async with factory() as resource:
                    close = anyio.Event()
                    self._closers.append((close, closed))
                    task_status.started(resource)
                    await opened.wait()
                    guard.shield = True
                    try:
                        await close.wait()
                    finally:
                        guard.shield = False
        finally:
            self._settle(opened)
            closed.set()

    def _settle(self, opened: anyio.Event) -> None:
        self._opening.discard(opened)
        opened.set()
