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

import anyio
import pytest

import dubbo.utils.dialer as dialer_module
from dubbo.utils import Dialer

pytestmark = pytest.mark.anyio


class _Peer:
    """A peer whose attempts wait for ``answer`` and then succeed or fail as ``refuse`` says."""

    def __init__(self) -> None:
        self.attempts = 0
        self.refuse = False
        self.answer = anyio.Event()
        self.answer.set()

    async def connect(self) -> int:
        self.attempts += 1
        await self.answer.wait()
        if self.refuse:
            raise ConnectionRefusedError(f"refused {self.attempts}")
        return self.attempts


async def _until(condition) -> None:
    with anyio.fail_after(5):
        while not condition():
            await anyio.sleep(0.001)


async def test_waiters_share_one_attempt_that_outlives_those_that_stop_waiting() -> None:
    peer = _Peer()
    peer.answer = anyio.Event()
    dialer = Dialer(peer.connect)
    results = []

    async def wait() -> None:
        results.append(await dialer.connect())

    with anyio.move_on_after(0.01):
        await dialer.connect()
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(wait)
        task_group.start_soon(wait)
        await anyio.wait_all_tasks_blocked()
        peer.answer.set()

    assert (peer.attempts, results) == (1, [1, 1])
    assert dialer.connected
    await dialer.aclose()


async def test_each_waiter_raises_its_own_copy_of_the_failure() -> None:
    peer = _Peer()
    peer.answer = anyio.Event()
    peer.refuse = True
    dialer = Dialer(peer.connect)
    raised = []

    async def wait() -> None:
        try:
            await dialer.connect()
        except ConnectionRefusedError as error:
            raised.append(error)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(wait)
        task_group.start_soon(wait)
        await anyio.wait_all_tasks_blocked()
        peer.answer.set()

    first, second = raised
    assert first is not second
    assert str(first) == str(second) == "refused 1"
    await dialer.aclose()


async def test_a_dialer_is_connected_from_a_success_until_a_failure(monkeypatch) -> None:
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.01] * 10))
    peer = _Peer()
    peer.refuse = True
    dialer = Dialer(peer.connect)
    assert not dialer.connected

    dialer.start()
    # Connects again in the background after each backoff.
    await _until(lambda: peer.attempts >= 3)
    assert not dialer.connected

    peer.refuse = False
    await _until(lambda: dialer.connected)
    await dialer.aclose()
    assert not dialer.connected


async def test_a_lost_connection_is_not_connected_until_the_attempt_after_the_backoff_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.05] * 10))
    peer = _Peer()
    dialer = Dialer(peer.connect)
    assert await dialer.connect() == 1
    assert dialer.connected

    dialer.lost()

    assert not dialer.connected
    assert peer.attempts == 1
    await _until(lambda: dialer.connected)
    assert peer.attempts == 2
    await dialer.aclose()


async def test_a_loss_reported_while_an_attempt_runs_is_left_to_that_attempt() -> None:
    peer = _Peer()
    peer.answer = anyio.Event()
    dialer = Dialer(peer.connect)
    dialer.start()
    await anyio.wait_all_tasks_blocked()

    dialer.lost()

    assert not dialer.connected
    peer.answer.set()
    assert await dialer.connect() == 1
    assert (peer.attempts, dialer.connected) == (1, True)
    await dialer.aclose()


async def test_closing_cancels_the_attempt_and_the_retry_and_connects_no_more(monkeypatch) -> None:
    monkeypatch.setattr(dialer_module, "backoff", lambda: iter([0.01] * 10))
    peer = _Peer()
    peer.answer = anyio.Event()
    dialer = Dialer(peer.connect)
    dialer.start()
    await anyio.wait_all_tasks_blocked()

    await dialer.aclose()
    dialer.start()
    dialer.lost()
    await anyio.sleep(0.05)

    assert peer.attempts == 1
    assert await dialer.connect() is None


async def test_a_failure_that_cannot_be_copied_reaches_the_waiter_as_it_is() -> None:
    class _Keyword(Exception):
        def __init__(self, message: str, *, code: int) -> None:
            super().__init__(message)
            self.code = code

    async def connect() -> int:
        raise _Keyword("refused", code=3)

    dialer = Dialer(connect)

    with pytest.raises(_Keyword, match="refused"):
        await dialer.connect()
    await dialer.aclose()
