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

from dubbo import Invocation, Invoke, Result
from dubbo.extension import extensions
from dubbo.filter import Filter, chain_filters, get_attempt_filters, get_service_filters
from dubbo.filter.accesslog import AccessLogFilter
from dubbo.filter.activecount import ActiveCountFilter
from dubbo.filter.actives import ActivesFilter
from dubbo.filter.deprecated import DeprecatedFilter
from dubbo.filter.executes import ExecutesFilter
from dubbo.filter.token import TokenFilter
from dubbo.filter.tps import TpsFilter
from dubbo.url import URL

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("side", "parameters", "expected"),
    [
        (
            "service",
            {"accesslog": "true", "token": "s", "getUser.tps": "2", "executes": "0", "service.filter": "named"},
            [AccessLogFilter, TokenFilter, TpsFilter, "named"],
        ),
        (
            "attempt",
            {"getUser.deprecated": "true", "actives": "2", "tps": "1", "reference.attempt-filter": "named"},
            [DeprecatedFilter, ActivesFilter, "named"],
        ),
        ("attempt", {"loadbalance": "leastactive"}, [ActiveCountFilter]),
        ("attempt", {"getUser.loadbalance": "leastactive"}, [ActiveCountFilter]),
        ("attempt", {"actives": "2", "loadbalance": "leastactive"}, [ActivesFilter]),
        ("service", {"accesslog": "false", "executes": "0", "deprecated": "false", "actives": "0"}, []),
        ("attempt", {"accesslog": "false", "executes": "0", "deprecated": "false", "actives": "0"}, []),
        ("attempt", {"loadbalance": "roundrobin"}, []),
        ("attempt", {"deprecated": "maybe"}, []),
    ],
    ids=[
        "service-before-named",
        "attempt-before-named",
        "least-active",
        "method-least-active",
        "actives-counting-for-least-active",
        "disabled-service",
        "disabled-attempt",
        "uncounted-round-robin",
        "unreadable-deprecated",
    ],
)
def test_settings_add_their_filters_before_named_filters(side, parameters, expected, isolated_extensions, url):
    class Named:
        def __init__(self, url: URL) -> None:
            pass

        async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
            return await call_next(invocation)

    extensions.register(Filter, "named", Named)
    configured = url.update_parameters(parameters)

    filters = get_service_filters(configured) if side == "service" else get_attempt_filters(configured)

    assert [type(filter_) for filter_ in filters] == [Named if item == "named" else item for item in expected]


@pytest.mark.parametrize("create", [ActiveCountFilter, ActivesFilter, DeprecatedFilter, ExecutesFilter, TpsFilter])
def test_a_filter_that_keeps_state_requires_the_application_that_keeps_it(create, url):
    with pytest.raises(RuntimeError, match="belongs to no application"):
        create(url.replace(attributes={}))


@pytest.mark.parametrize(
    ("create", "key"),
    [(ActivesFilter, "actives"), (ExecutesFilter, "executes"), (TpsFilter, "tps")],
    ids=["actives", "executes", "tps"],
)
async def test_a_negative_limit_limits_no_call(create, key, ending, call, url):
    limited = create(url.update_parameters({key: "-1"}))
    end = ending(Result())

    with anyio.fail_after(5):
        results = [await limited.invoke(end.invoke, call()) for _ in range(2)]

    assert results == [Result(), Result()]


async def test_a_chain_keeps_the_invoker_url_and_closes_the_invoker(ending, url):
    end = ending(Result())
    invoker = chain_filters(end, [AccessLogFilter(url), AccessLogFilter(url)])

    assert invoker.url is end.url
    await invoker.aclose()

    assert end.closed is True


def test_a_chain_without_filters_is_the_original_invoker(ending):
    end = ending(Result())

    assert chain_filters(end, []) is end


async def test_a_filter_chain_runs_first_outermost_and_can_change_the_response(ending, call):
    events = []

    class Record:
        def __init__(self, name: str) -> None:
            self.name = name

        async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
            events.append(f"{self.name}>")
            result = await call_next(invocation)
            events.append(f"<{self.name}")
            result.attachments[self.name] = "seen"

            return result

    end = ending(Result(value="ok", attachments={"audit-id": "1"}))
    invoker = chain_filters(end, [Record("outer"), Record("inner")])

    result = await invoker.invoke(call())

    assert (result.value, result.error, dict(result.attachments), events) == (
        "ok",
        None,
        {"audit-id": "1", "inner": "seen", "outer": "seen"},
        ["outer>", "inner>", "<inner", "<outer"],
    )


async def test_a_filter_can_answer_without_calling_the_next_invoker(ending, call):
    class Answer:
        async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
            return Result(value="cached")

    end = ending(Result(value="uncached"))

    result = await chain_filters(end, [Answer()]).invoke(call())

    assert (result, end.calls) == (Result(value="cached"), [])
