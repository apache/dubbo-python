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

import asyncio
import functools
import itertools
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest

from dubbo.utils import Latest, create_background_task_group, follow, release_scope, wait_then_cancel

pytestmark = pytest.mark.anyio


async def test_tasks_that_finish_within_the_grace_are_not_cancelled() -> None:
    task = asyncio.get_running_loop().create_task(asyncio.sleep(0.01, "done"))

    await wait_then_cancel({task}, 1)

    assert task.result() == "done"


async def test_tasks_still_running_after_the_grace_are_cancelled() -> None:
    task = asyncio.get_running_loop().create_task(asyncio.sleep(10))

    await wait_then_cancel({task}, 0.01)

    assert task.cancelled()


async def test_cancelling_the_wait_cancels_the_tasks_at_once_and_waits_for_them() -> None:
    finished = []

    async def handler() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0)
            finished.append(True)

    task = asyncio.get_running_loop().create_task(handler())

    with anyio.move_on_after(0.01):
        await wait_then_cancel({task}, 10)

    assert task.cancelled()
    assert finished == [True]


async def test_a_task_that_ignores_cancellation_is_logged_and_left_running(caplog: pytest.LogCaptureFixture) -> None:
    release = asyncio.Event()

    async def stubborn() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await release.wait()

    task = asyncio.get_running_loop().create_task(stubborn())
    await asyncio.sleep(0)

    with caplog.at_level(logging.WARNING):
        await wait_then_cancel({task}, 0.01)

    assert not task.done()
    assert "1 tasks kept running after being cancelled" in caplog.text
    release.set()
    await task


async def test_each_iteration_of_a_latest_starts_with_the_current_value_and_skips_older_ones() -> None:
    latest: Latest[int] = Latest()
    latest.publish(1)
    first, second = aiter(latest), aiter(latest)

    assert await anext(first) == 1
    latest.publish(2)
    latest.publish(3)

    assert await anext(first) == 3
    assert await anext(second) == 3


async def test_closing_a_latest_ends_its_iterations_after_the_last_value() -> None:
    latest: Latest[int] = Latest()
    latest.publish(1)
    latest.close()
    latest.publish(2)

    assert [value async for value in latest] == [1]


async def test_closing_a_latest_ends_an_iteration_waiting_for_a_value() -> None:
    latest: Latest[int] = Latest()
    values: list[int] = []

    async def read() -> None:
        values.extend([value async for value in latest])

    with anyio.fail_after(5):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(read)
            await anyio.wait_all_tasks_blocked()
            latest.close()

    assert values == []


async def test_closing_a_latest_with_an_error_raises_it_from_its_iterations() -> None:
    latest: Latest[int] = Latest()
    values = aiter(latest)
    latest.close(RuntimeError("ended"))

    with pytest.raises(RuntimeError, match="ended"):
        await anext(values)


class _Subscriptions:
    """Subscriptions that each fail, end, or yield their values and then wait, in turn."""

    def __init__(self, *outcomes: Exception | list[int]) -> None:
        self.outcomes = list(outcomes)
        self.count = 0

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[int]]:
        outcome = self.outcomes[min(self.count, len(self.outcomes) - 1)]
        self.count += 1
        if isinstance(outcome, Exception):
            raise outcome

        async def values() -> AsyncIterator[int]:
            for value in outcome:
                yield value
            if self.count >= len(self.outcomes):
                await anyio.sleep_forever()

        yield values()


async def _follow(subscriptions: _Subscriptions, received: list[int], **options: bool) -> None:
    async def receive(value: int) -> None:
        received.append(value)

    async with anyio.create_task_group() as task_group:
        await task_group.start(functools.partial(follow, subscriptions.subscribe, receive, "numbers", **options))
        with anyio.fail_after(5):
            while len(received) < 2:
                await anyio.sleep(0)
        task_group.cancel_scope.cancel()


async def test_follow_subscribes_again_when_a_subscription_fails_or_ends(monkeypatch) -> None:
    monkeypatch.setattr("dubbo.utils.async_.backoff", lambda: itertools.repeat(0))
    subscriptions = _Subscriptions([1], RuntimeError("down"), [], [2])
    received: list[int] = []

    await _follow(subscriptions, received)

    assert received == [1, 2]
    assert subscriptions.count == 4


async def test_follow_raises_a_failure_before_the_first_value() -> None:
    async def receive(value: int) -> None:
        pass

    with pytest.raises(RuntimeError, match="down"):
        await follow(_Subscriptions(RuntimeError("down")).subscribe, receive, "numbers")


async def test_follow_may_retry_a_failure_before_the_first_value(monkeypatch) -> None:
    monkeypatch.setattr("dubbo.utils.async_.backoff", lambda: itertools.repeat(0))
    received: list[int] = []

    await _follow(_Subscriptions(RuntimeError("down"), [1, 2]), received, retry_first=True)

    assert received == [1, 2]


@pytest.mark.anyio
async def test_a_background_task_group_raises_the_body_exception_as_it_is() -> None:
    cancelled = []

    async def serve() -> None:
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.append(True)

    async def start() -> None:
        async with create_background_task_group() as task_group:
            task_group.start_soon(serve)
            await anyio.sleep(0)
            raise ConnectionRefusedError

    with pytest.raises(ConnectionRefusedError):
        await start()

    assert cancelled == [True]


@pytest.mark.anyio
async def test_a_background_task_group_groups_the_exceptions_of_its_tasks() -> None:
    async def fail() -> None:
        raise ConnectionRefusedError

    with pytest.raises(ExceptionGroup) as raised:
        async with create_background_task_group() as task_group:
            task_group.start_soon(fail)

    assert raised.group_contains(ConnectionRefusedError)


@pytest.mark.anyio
async def test_a_background_task_group_raises_the_body_exception_with_those_of_failed_tasks() -> None:
    async def fail_when_cancelled() -> None:
        try:
            await anyio.sleep_forever()
        finally:
            raise ConnectionResetError

    async def start() -> None:
        async with create_background_task_group() as task_group:
            task_group.start_soon(fail_when_cancelled)
            await anyio.sleep(0)
            raise ConnectionRefusedError

    with pytest.raises(ExceptionGroup) as raised:
        await start()

    assert raised.group_contains(ConnectionRefusedError)
    assert raised.group_contains(ConnectionResetError)


async def test_an_iteration_of_latest_reads_on_after_a_cancelled_wait() -> None:
    latest: Latest[int] = Latest()
    reader = aiter(latest)

    with anyio.move_on_after(0.01):
        await anext(reader)
    latest.publish(1)

    with anyio.fail_after(5):
        assert await anext(reader) == 1


async def test_a_release_runs_to_its_end_unless_its_caller_is_cancelled_meanwhile() -> None:
    finished = []

    with release_scope(5):
        await anyio.sleep(0.01)
        finished.append("graceful")

    # A graceful release stays cancellable; a shielded one would hold up the task group past the bound.
    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:

            async def endless_release() -> None:
                with release_scope(10):
                    await anyio.sleep_forever()

            tasks.start_soon(endless_release)
            await anyio.wait_all_tasks_blocked()
            tasks.cancel_scope.cancel()

    assert finished == ["graceful"]


async def test_a_cancelled_caller_gives_a_release_a_shielded_moment() -> None:
    finished = []

    with anyio.CancelScope() as caller:
        caller.cancel()
        try:
            await anyio.sleep(1)
        finally:
            # The release outlives the cancellation, but not by much.
            with release_scope(10):
                await anyio.sleep(0.05)
                finished.append("short")
            with release_scope(10):
                await anyio.sleep_forever()

    assert finished == ["short"]
