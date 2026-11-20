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

"""Async helpers: tasks ended after a grace period, tasks behind a body, latest values, and subscriptions kept up."""

import asyncio
import logging
import math
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Collection
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Generic, TypeVar, cast

import anyio
from anyio.abc import TaskGroup, TaskStatus

from .backoff import backoff

__all__ = [
    "Latest",
    "close_then_abort",
    "create_background_task_group",
    "follow",
    "release_scope",
    "release_shield",
    "wait_then_cancel",
]

T = TypeVar("T")

_logger = logging.getLogger(__name__)

# Seconds that what is cancelled gets to release what it holds, waiting on no peer.
_RELEASE_TIMEOUT = 1.0
# Seconds a closing connection waits for the peer to read what was written.
_CLOSE_GRACE = 1.0


def release_scope(graceful: float) -> anyio.CancelScope:
    """Return the scope of a release that waits on a peer, such as unsubscribing or closing a session.

    Unless the caller is cancelled, the release may take ``graceful`` seconds
    and its caller's cancellation cuts it short. A cancelled caller stops at
    once, so the release then gets only a short, shielded moment.
    """
    if anyio.current_effective_deadline() == -math.inf:
        return release_shield()
    return anyio.move_on_after(graceful)


def release_shield() -> anyio.CancelScope:
    """Return the shielded scope of a moment in which what is cancelled releases what it holds, waiting on no peer.

    Aborting sockets and cancelling tasks take it, as they need no answer.
    """
    return anyio.move_on_after(_RELEASE_TIMEOUT, shield=True)


async def close_then_abort(
    wait_closed: Callable[[], Awaitable[object]], closed: Callable[[], bool], abort: Callable[[], None]
) -> None:
    """Wait a moment for a close already begun to finish, then abort what is still open.

    A cancelled wait aborts at once. The abort is awaited under a
    `release_shield`.
    """
    try:
        with anyio.move_on_after(_CLOSE_GRACE):
            await wait_closed()
    finally:
        if not closed():
            abort()
            with release_shield():
                await wait_closed()


async def wait_then_cancel(tasks: Collection[asyncio.Task[Any]], grace: float) -> None:
    """Wait up to ``grace`` seconds for ``tasks`` to finish, then cancel the rest and wait as long again for them.

    Tasks that still run after that are logged and left running. Cancelling
    the wait cancels the tasks at once and waits up to a second for them.
    """
    if not tasks:
        return

    try:
        _, pending = await asyncio.wait(tasks, timeout=grace)
        if not pending:
            return

        for task in pending:
            task.cancel()
        _, stuck = await asyncio.wait(pending, timeout=grace)
    except BaseException:
        cancelled = [task for task in tuple(tasks) if task.cancel()]
        if cancelled:
            with release_shield():
                await asyncio.wait(cancelled)
        raise

    if stuck:
        _logger.warning("%d tasks kept running after being cancelled", len(stuck))


@asynccontextmanager
async def create_background_task_group() -> AsyncGenerator[TaskGroup]:
    """Open a task group for the background tasks of the body, as `anyio.create_task_group` does, except that when only the body fails its exception is raised alone, not in a group.

    A failure to start, such as that of a first subscription, so keeps its
    type. When tasks fail too, every exception stays in the group.
    """
    failure: Exception | None = None
    try:
        async with anyio.create_task_group() as task_group:
            try:
                yield task_group
            except Exception as error:
                failure = error
                raise
    except BaseExceptionGroup as group:
        if failure is None or group.exceptions != (failure,):
            raise
    else:
        return

    # Raised outside the handler, so that the group does not become the context of the exception it holds.
    raise failure


class Latest(Generic[T]):
    """The latest of the values published in the event loop, which each iteration reads, skipping older ones.

    Every ``async for`` reads on its own, starting with the current value, if
    any. `close` ends every iteration once it has read the last value. It is
    not thread-safe: publish and close in the event loop; from another
    thread, go through ``anyio.from_thread.run_sync``.
    """

    def __init__(self) -> None:
        self._value: T | None = None
        self._version = 0
        self._closed = False
        self._error: BaseException | None = None
        self._changed = anyio.Event()

    @property
    def closed(self) -> bool:
        """Whether `close` has been called."""
        return self._closed

    @property
    def empty(self) -> bool:
        """Whether nothing has been published yet."""
        return self._version == 0

    def publish(self, value: T) -> None:
        """Make ``value`` the next one each iteration reads, replacing one not yet read; ignored once closed."""
        if self._closed:
            return

        self._value = value
        self._version += 1
        self._changed.set()
        self._changed = anyio.Event()

    def close(self, error: BaseException | None = None) -> None:
        """End every iteration after its last value, raising ``error`` if given."""
        if self._closed:
            return

        self._closed, self._error = True, error
        self._changed.set()

    def __aiter__(self) -> AsyncIterator[T]:
        return _LatestReader(self)


class _LatestReader(AsyncIterator[T]):
    """One iteration of a `Latest`; a cancelled wait for the next value leaves it able to read on, unlike a generator."""

    def __init__(self, latest: Latest[T]) -> None:
        self._latest = latest
        self._seen = 0

    async def __anext__(self) -> T:
        latest = self._latest
        while self._seen == latest._version:
            if latest._closed:
                if latest._error is not None:
                    raise latest._error
                raise StopAsyncIteration
            await latest._changed.wait()

        self._seen = latest._version
        # Something was published, so the value is set.
        return cast(T, latest._value)


async def follow(
    subscribe: Callable[[], AbstractAsyncContextManager[AsyncIterator[T]]],
    receive: Callable[[T], Awaitable[None]],
    name: str,
    *,
    retry_first: bool = False,
    task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
) -> None:
    """Hand ``receive`` each value of ``subscribe()`` until cancelled, subscribing again after a delay when it fails or ends.

    ``task_status`` starts with the first value. A failure before it is
    raised, unless ``retry_first``, which starts ``task_status`` and tries
    again. Later failures are logged with ``name``, what is followed. A
    failure of ``receive`` counts as one of the subscription.
    """
    started = False
    delays = backoff()
    while True:
        try:
            async with subscribe() as values:
                async for value in values:
                    await receive(value)
                    delays = backoff()
                    if not started:
                        started = True
                        task_status.started()
            _logger.warning("Following %s ended; subscribing again", name)
        except Exception:
            if not started and not retry_first:
                raise
            _logger.warning("Following %s failed; subscribing again", name, exc_info=True)

        if not started:
            started = True
            task_status.started()
        await anyio.sleep(next(delays))
