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

from dubbo import Invocation, Result
from dubbo.filter.activecount import ActiveCountFilter, active_counts

pytestmark = pytest.mark.anyio


async def test_active_count_tracks_calls_per_method_until_they_finish(gate, call, url):
    filter_ = ActiveCountFilter(url)
    counts = active_counts(url)

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(filter_.invoke, gate.invoke, call("wait"))
            tasks.start_soon(filter_.invoke, gate.invoke, call("wait"))
            await anyio.wait_all_tasks_blocked()
            assert (counts.get(url, "wait"), counts.get(url, "other")) == (2, 0)
            gate.opened.set()

    assert counts.get(url, "wait") == 0


async def test_active_count_releases_the_count_when_the_next_invoker_raises(call, url):
    counts = active_counts(url)

    async def fail(invocation: Invocation) -> Result:
        assert counts.get(url, "fail") == 1
        raise RuntimeError("down")

    with pytest.raises(RuntimeError, match="down"):
        await ActiveCountFilter(url).invoke(fail, call("fail"))

    assert counts.get(url, "fail") == 0
