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

from dubbo.protocol.served import ClientPool

pytestmark = pytest.mark.anyio


class _Client:
    def __init__(self) -> None:
        self.closed = False

    async def __aenter__(self) -> "_Client":
        return self

    async def aclose(self) -> None:
        self.closed = True


async def test_the_last_share_given_back_closes_a_pooled_client() -> None:
    pool: ClientPool[_Client] = ClientPool()
    first = await pool.acquire("a", _Client)
    second = await pool.acquire("a", _Client)

    await pool.release(first)
    assert second is first
    assert not first.closed

    await pool.release(second)
    assert first.closed
    await pool.aclose()


async def test_a_share_given_back_after_its_client_closed_changes_nothing() -> None:
    pool: ClientPool[_Client] = ClientPool()
    first = await pool.acquire("a", _Client)
    await pool.release(first)

    await pool.release(first)
    replacement = await pool.acquire("a", _Client)

    assert replacement is not first
    assert not replacement.closed
    await pool.aclose()


async def test_a_share_taken_while_a_duplicate_client_closes_keeps_the_shared_one_open() -> None:
    connected = anyio.Event()
    first_share_given_back = anyio.Event()
    shares: list[_Client] = []

    class SlowClient(_Client):
        async def __aenter__(self) -> "SlowClient":
            await connected.wait()
            return self

        async def aclose(self) -> None:
            if self not in shares:
                await first_share_given_back.wait()
            await super().aclose()

    pool: ClientPool[_Client] = ClientPool()

    async def acquire() -> None:
        shares.append(await pool.acquire("a", SlowClient))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(acquire)
        task_group.start_soon(acquire)
        await anyio.wait_all_tasks_blocked()
        connected.set()
        while not shares:
            await anyio.wait_all_tasks_blocked()

        await pool.release(shares[0])
        first_share_given_back.set()

    assert shares[1] is shares[0]
    assert not shares[0].closed
    await pool.aclose()


async def test_a_closed_pool_closes_its_clients_and_lends_no_more() -> None:
    pool: ClientPool[_Client] = ClientPool()
    client = await pool.acquire("a", _Client)

    await pool.aclose()

    assert client.closed
    with pytest.raises(RuntimeError, match="closed"):
        await pool.acquire("a", _Client)


async def test_closing_the_pool_closes_every_client_even_when_one_fails_to_close() -> None:
    class _Failing(_Client):
        async def aclose(self) -> None:
            await super().aclose()
            raise OSError("cannot close")

    pool: ClientPool[_Client] = ClientPool()
    failing = await pool.acquire("a", _Failing)
    other = await pool.acquire("b", _Client)

    with pytest.raises(OSError, match="cannot close"):
        await pool.aclose()

    assert (failing.closed, other.closed) == (True, True)
