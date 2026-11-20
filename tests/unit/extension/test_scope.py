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

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import anyio
import pytest

from dubbo.extension import ApplicationScope, Resource


class Connections:
    """Open fake connections and record when each opens and closes."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.fail = False

    def connect(self, address: str) -> "Connection":
        return Connection(self, address)


class Connection(Resource):
    def __init__(self, connections: Connections, address: str) -> None:
        self.connections = connections
        self.address = address

    async def __aenter__(self) -> "Connection":
        self.connections.events.append(f"open {self.address}")
        await anyio.sleep(0.01)
        if self.connections.fail:
            raise ConnectionRefusedError(self.address)
        return self

    async def aclose(self) -> None:
        self.connections.events.append(f"close {self.address}")
        await anyio.sleep(0.01)


@pytest.mark.anyio
async def test_scope_opens_each_key_once_and_closes_in_reverse_order() -> None:
    connections = Connections()

    async with ApplicationScope() as scope:
        first = await scope.share("a", lambda: connections.connect("a"))
        again = await scope.share("a", lambda: connections.connect("a"))
        other = await scope.share("b", lambda: connections.connect("b"))
        assert first is again
        assert other is not first
        assert connections.events == ["open a", "open b"]

    assert connections.events[2:] == ["close b", "close a"]


@pytest.mark.anyio
async def test_failed_opening_is_retried_by_the_next_request() -> None:
    connections = Connections()
    connections.fail = True

    async with ApplicationScope() as scope:
        with pytest.raises(ConnectionRefusedError):
            await scope.share("a", lambda: connections.connect("a"))

        connections.fail = False
        assert (await scope.share("a", lambda: connections.connect("a"))).address == "a"

    assert connections.events == ["open a", "open a", "close a"]


@pytest.mark.anyio
async def test_any_task_shares_while_the_scope_is_open() -> None:
    connections = Connections()
    shared = []

    async with ApplicationScope() as scope:

        async def share() -> None:
            shared.append(await scope.share("a", lambda: connections.connect("a")))

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(share)
            tasks.start_soon(share)

        assert shared[0] is shared[1]

    assert connections.events == ["open a", "close a"]

    with pytest.raises(RuntimeError, match="not open"):
        await scope.share("a", lambda: connections.connect("a"))


@pytest.mark.anyio
async def test_a_user_that_shares_while_it_opens_closes_before_the_shared_resource() -> None:
    connections = Connections()

    class User(Resource):
        def __init__(self, scope: ApplicationScope) -> None:
            self.scope = scope

        async def __aenter__(self) -> "User":
            await self.scope.share("a", lambda: connections.connect("a"))
            return self

        async def aclose(self) -> None:
            connections.events.append("close user")

    async with AsyncExitStack() as stack:
        scope = await stack.enter_async_context(ApplicationScope())
        await stack.enter_async_context(User(scope))

    assert connections.events == ["open a", "close user", "close a"]


@pytest.mark.anyio
async def test_a_cancelled_scope_closes_what_it_shares_at_once() -> None:
    connections = Connections()

    with anyio.CancelScope() as cancelled:
        async with ApplicationScope() as scope:
            await scope.share("a", lambda: connections.connect("a"))
            cancelled.cancel()
            await anyio.sleep_forever()

    assert connections.events == ["open a", "close a"]


@pytest.mark.anyio
async def test_a_shared_resource_may_share_another_while_it_opens() -> None:
    connections = Connections()

    @asynccontextmanager
    async def user(scope: ApplicationScope) -> AsyncIterator[str]:
        await scope.share("a", lambda: connections.connect("a"))
        yield "user"
        connections.events.append("close user")

    async with ApplicationScope() as scope:
        assert await scope.share("user", lambda: user(scope)) == "user"

    assert connections.events == ["open a", "close user", "close a"]


@pytest.mark.anyio
async def test_a_shared_resource_may_hold_a_task_group() -> None:
    stopped = []

    @asynccontextmanager
    async def worker() -> AsyncIterator[None]:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(anyio.sleep_forever)
            yield
            tasks.cancel_scope.cancel()
        stopped.append(True)

    async with ApplicationScope() as scope:
        await scope.share("worker", worker)

    assert stopped == [True]


@pytest.mark.anyio
async def test_a_failing_task_of_a_shared_resource_exits_it_and_fails_the_scope_with_its_error() -> None:
    failing, exited = anyio.Event(), []

    @asynccontextmanager
    async def worker() -> AsyncIterator[None]:
        async def fail() -> None:
            await failing.wait()
            raise ValueError("the worker failed")

        try:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(fail)
                yield
        finally:
            exited.append(True)

    async def run() -> None:
        async with ApplicationScope() as scope:
            await scope.share("worker", worker)
            failing.set()
            await anyio.sleep_forever()

    with pytest.raises(ExceptionGroup) as raised:
        await run()

    assert raised.group_contains(ValueError, match="the worker failed", depth=None)
    assert exited == [True]


@pytest.mark.anyio
async def test_closing_waits_for_a_resource_still_opening_and_closes_it() -> None:
    opening, leaving, events = anyio.Event(), anyio.Event(), []

    @asynccontextmanager
    async def slow() -> AsyncIterator[str]:
        opening.set()
        await leaving.wait()
        events.append("open")
        yield "slow"
        events.append("close")

    async with anyio.create_task_group() as tasks, ApplicationScope() as scope:
        tasks.start_soon(scope.share, "slow", slow)
        await opening.wait()
        # Closing begins before the resource goes on opening.
        leaving.set()

    assert events == ["open", "close"]


@pytest.mark.anyio
async def test_cancelling_a_request_cancels_the_opening() -> None:
    connections = Connections()

    @asynccontextmanager
    async def slow() -> AsyncIterator[str]:
        await anyio.sleep_forever()
        yield "never"

    async with ApplicationScope() as scope:
        with anyio.fail_after(5), anyio.move_on_after(0.05):
            await scope.share("slow", slow)

        assert (await scope.share("a", lambda: connections.connect("a"))).address == "a"

    assert connections.events == ["open a", "close a"]


@pytest.mark.anyio
async def test_cancelling_a_request_as_the_resource_opens_exits_the_resource() -> None:
    events = []

    async with ApplicationScope() as scope:
        with anyio.CancelScope() as request:

            @asynccontextmanager
            async def cancelling() -> AsyncIterator[str]:
                request.cancel()
                try:
                    yield "opened"
                finally:
                    events.append("close")

            await scope.share("a", cancelling)

        assert events == ["close"]


@pytest.mark.anyio
async def test_the_state_of_an_application_lasts_until_its_scope_closes() -> None:
    async with ApplicationScope() as scope:
        kept = scope.state.setdefault(Connections, Connections())
        again = scope.state.setdefault(Connections, Connections())

    assert again is kept
    assert scope.state == {}
