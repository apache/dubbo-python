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

import pytest

from dubbo import RemoteError, Result, RpcError, Status

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "error",
    [RpcError(Status.UNAVAILABLE, "down"), RemoteError("java.lang.IllegalStateException", "bad")],
    ids=["unavailable", "remote-exception"],
)
async def test_failsafe_logs_the_failure_and_returns_nothing(error, provider, open_cluster, call, caplog):
    async with open_cluster("failsafe", provider("a", Result(error=error))) as cluster:
        result = await cluster.invoke(call)

    assert result == Result()
    assert [(record.name, record.levelno, record.exc_info[1]) for record in caplog.records] == [
        ("dubbo.cluster.failsafe", logging.WARNING, error)
    ]


@pytest.mark.parametrize("streaming", [False, True], ids=["successful-unary", "failed-stream-opening"])
async def test_failsafe_preserves_successes_and_stream_opening_failures(
    streaming, provider, unavailable, open_cluster, call, streaming_call
):
    expected = unavailable if streaming else Result(value="ok")

    async with open_cluster("failsafe", provider("a", expected)) as cluster:
        result = await cluster.invoke(streaming_call if streaming else call)

    assert result is expected
