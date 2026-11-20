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

import anyio
import pytest

from dubbo import RemoteError, Result
from dubbo.cluster import failback

pytestmark = pytest.mark.anyio


@pytest.fixture
def retry_timer(monkeypatch):
    monkeypatch.setattr(failback, "_RETRY_INTERVAL", 0)


async def test_failback_returns_nothing_and_retries_until_the_first_success(
    retry_timer, provider, unavailable, open_cluster, call, caplog
):
    remote = provider("a", unavailable, unavailable, Result(value="ok"), unavailable)

    async with open_cluster("failback", remote) as cluster:
        assert await cluster.invoke(call) == Result()
        await anyio.wait_all_tasks_blocked()

    assert remote.calls == 3
    assert [(record.name, record.levelno, record.exc_info[1]) for record in caplog.records] == [
        ("dubbo.cluster.failback", logging.WARNING, unavailable.error)
    ]


async def test_failback_retries_on_a_different_candidate_than_the_last(
    retry_timer, provider, unavailable, open_cluster, call
):
    down, up = provider("a", unavailable), provider("b", Result(value="ok"))

    async with open_cluster("failback", down, up) as cluster:
        result = await cluster.invoke(call)
        await anyio.wait_all_tasks_blocked()

    assert (result, down.calls, up.calls) == (Result(), 1, 1)


@pytest.mark.parametrize(
    ("query", "calls", "levels"),
    [
        ("", 4, [logging.WARNING, logging.ERROR]),
        ("retries=1", 2, [logging.WARNING, logging.ERROR]),
        ("retries=0", 1, [logging.WARNING]),
    ],
    ids=["default", "one-retry", "no-retry"],
)
async def test_failback_drops_a_call_after_its_retry_budget(
    retry_timer, query, calls, levels, provider, unavailable, open_cluster, call, caplog
):
    remote = provider("a", unavailable)

    async with open_cluster("failback", remote, query=query) as cluster:
        assert await cluster.invoke(call) == Result()
        await anyio.wait_all_tasks_blocked()

    assert remote.calls == calls
    assert [record.levelno for record in caplog.records] == levels


@pytest.mark.parametrize("streaming", [False, True], ids=["remote-exception", "failed-stream-opening"])
async def test_failback_does_not_retry_a_method_exception_or_stream_opening(
    streaming, provider, unavailable, open_cluster, call, streaming_call
):
    failed = unavailable if streaming else Result(error=RemoteError("java.lang.IllegalStateException", "bad"))
    remote = provider("a", failed)

    async with open_cluster("failback", remote) as cluster:
        result = await cluster.invoke(streaming_call if streaming else call)
        await anyio.wait_all_tasks_blocked()

    assert (result, remote.calls) == (failed, 1)


async def test_failback_drops_overflow_and_cancels_queued_retries_when_closed(
    provider, unavailable, open_cluster, call, caplog
):
    remote = provider("a", unavailable)

    async with open_cluster("failback", remote, query="failbacktasks=1") as cluster:
        assert await cluster.invoke(call) == Result()
        assert await cluster.invoke(call) == Result()

    assert (remote.calls, remote.closed) == (2, True)
    assert [(record.name, record.levelno) for record in caplog.records] == [
        ("dubbo.cluster.failback", logging.WARNING),
        ("dubbo.cluster.failback", logging.ERROR),
    ]


@pytest.mark.parametrize("query", ["retries=-1", "failbacktasks=0"], ids=["negative-retries", "no-queue-capacity"])
async def test_failback_refuses_invalid_retry_settings(query, open_cluster):
    with pytest.raises(ValueError, match="retries must not be negative and failbacktasks must be positive"):
        async with open_cluster("failback", query=query):
            pass
