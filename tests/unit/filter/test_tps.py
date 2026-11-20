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

from types import SimpleNamespace

import pytest

from dubbo import Result, RpcError, Status
from dubbo.filter import tps
from dubbo.filter.tps import TpsFilter

pytestmark = pytest.mark.anyio


async def test_tps_counts_methods_together_except_those_with_their_own_windows(monkeypatch, ending, call, url):
    now = [0.0]
    monkeypatch.setattr(tps, "time", SimpleNamespace(monotonic=lambda: now[0]))
    filter_ = TpsFilter(
        url.update_parameters({"tps": "2", "tps.interval": "60000", "own.tps": "1", "own.tps.interval": "50"})
    )
    end = ending(Result())

    shared = [await filter_.invoke(end.invoke, call(method)) for method in "aba"]
    own = [await filter_.invoke(end.invoke, call("own")) for _ in range(2)]
    now[0] = 0.05
    renewed = await filter_.invoke(end.invoke, call("own"))
    shared_after = await filter_.invoke(end.invoke, call("a"))

    assert shared[:2] == [Result(), Result()]
    assert own[0] == renewed == Result()
    errors = [shared[2].error, own[1].error, shared_after.error]
    assert all(isinstance(error, RpcError) for error in errors)
    assert [(error.status, error.message) for error in errors] == [
        (Status.UNAVAILABLE, "com.example.UserService.a serves 2 calls in 60.0 seconds"),
        (Status.UNAVAILABLE, "com.example.UserService.own serves 1 calls in 0.05 seconds"),
        (Status.UNAVAILABLE, "com.example.UserService.a serves 2 calls in 60.0 seconds"),
    ]
    assert [invocation.method for invocation in end.calls] == ["a", "b", "own", "own"]


async def test_tps_made_again_keeps_the_calls_its_window_counted_under_the_new_rate(ending, call, url):
    end = ending(Result())
    before = TpsFilter(url.update_parameters({"tps": "2"}))

    counted = [await before.invoke(end.invoke, call()) for _ in range(2)]
    same = await TpsFilter(url.update_parameters({"tps": "2"})).invoke(end.invoke, call())
    raised = TpsFilter(url.update_parameters({"tps": "3"}))
    after = [await raised.invoke(end.invoke, call()) for _ in range(2)]

    assert counted == [Result(), Result()]
    assert isinstance(same.error, RpcError)
    assert after[0] == Result()
    assert isinstance(after[1].error, RpcError)
    assert len(end.calls) == 3
