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

import itertools
from contextlib import asynccontextmanager

import anyio
import attrs
import pytest

from dubbo.cluster import Router
from dubbo.cluster.directory import DynamicDirectory
from dubbo.rpc.definition import Method
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import PROVIDER_URL, URL
from dubbo.utils import Latest

pytestmark = pytest.mark.anyio
CALL = Invocation(interface="test.Greeter", method="greet", definition=Method(name="greet", request=(), response=None))


@attrs.define(kw_only=False)
class _Invoker(Invoker):
    url: URL
    closed: bool = False
    closing: anyio.Event = attrs.field(factory=anyio.Event)

    async def invoke(self, invocation):
        return Result()

    async def aclose(self):
        self.closed = True
        self.closing.set()


@asynccontextmanager
async def _fixed(urls):
    async def snapshots():
        yield urls
        await anyio.sleep_forever()

    yield snapshots()


async def test_different_service_groups_at_one_address_keep_distinct_invokers():
    urls = [
        URL.parse(f"tri://10.0.0.5:50051/test.Greeter?group={group}&version={version}")
        for group, version in (("a", "1"), ("b", "2"))
    ]

    async def refer(url):
        return _Invoker(url)

    async with DynamicDirectory(lambda: _fixed(urls), refer, "test.Greeter") as directory:
        assert [invoker.url for invoker in directory.candidates(CALL)] == urls


@pytest.mark.parametrize("error", [TypeError, ValueError, OSError])
async def test_a_provider_that_cannot_be_called_is_left_out_of_the_others(error):
    unfit, fit = URL.parse("dubbo://a:1/test.Greeter"), URL.parse("tri://b:1/test.Greeter")

    async def refer(url):
        if url is unfit:
            raise error("the protocol cannot carry the methods")
        return _Invoker(url)

    with anyio.fail_after(5):
        async with DynamicDirectory(lambda: _fixed([unfit, fit]), refer, "test.Greeter") as directory:
            assert [invoker.url for invoker in directory.candidates(CALL)] == [fit]


async def test_an_unchanged_provider_keeps_its_invoker_whatever_the_protocol_adds_to_its_url():
    first, second = URL.parse("dubbo://a:1/test.Greeter"), URL.parse("dubbo://b:1/test.Greeter")
    snapshots = Latest()
    snapshots.publish([first])
    referred = []

    async def refer(url):
        # As a protocol that fills in its defaults.
        invoker = _Invoker(url.update_parameters({"serialization": "hessian2"}))
        referred.append(invoker)
        return invoker

    @asynccontextmanager
    async def changing():
        yield aiter(snapshots)

    with anyio.fail_after(5):
        async with DynamicDirectory(changing, refer, "test.Greeter") as directory:
            snapshots.publish([first, second])
            while len(directory.candidates(CALL)) < 2:
                await anyio.sleep(0.001)

            assert len(referred) == 2
            assert not referred[0].closed


async def test_removed_providers_close_while_unchanged_providers_keep_their_invokers():
    first, second = URL.parse("tri://a:1/test.Greeter"), URL.parse("tri://b:1/test.Greeter")
    snapshots = Latest()
    snapshots.publish([first, second])
    referred = []

    async def refer(url):
        invoker = _Invoker(url)
        referred.append(invoker)
        return invoker

    @asynccontextmanager
    async def changing():
        yield aiter(snapshots)

    with anyio.fail_after(5):
        async with DynamicDirectory(changing, refer, "test.Greeter") as directory:
            snapshots.publish([second])
            await referred[0].closing.wait()

            assert directory.candidates(CALL) == (referred[1],)
            assert [invoker.closed for invoker in referred] == [True, False]

    assert [invoker.closed for invoker in referred] == [True, True]


async def test_a_provider_that_publishes_new_parameters_gets_a_new_invoker_for_the_same_call_url():
    published = URL.parse("tri://a:1/test.Greeter?zone=east")
    calls = URL.parse("tri://a:1/test.Greeter")
    snapshots = Latest()
    snapshots.publish([calls.replace(attributes={PROVIDER_URL: published})])
    referred = []

    async def refer(url):
        invoker = _Invoker(url)
        referred.append(invoker)
        return invoker

    @asynccontextmanager
    async def changing():
        yield aiter(snapshots)

    with anyio.fail_after(5):
        async with DynamicDirectory(changing, refer, "test.Greeter") as directory:
            snapshots.publish([calls.replace(attributes={PROVIDER_URL: published.update_parameters({"zone": "west"})})])
            await referred[0].closing.wait()

            assert directory.candidates(CALL) == (referred[1],)
            assert referred[1].url.attributes[PROVIDER_URL].parameters["zone"] == "west"


async def test_a_router_that_fails_to_take_the_providers_leaves_each_invoker_closed():
    first, second = URL.parse("tri://a:1/test.Greeter"), URL.parse("tri://b:1/test.Greeter")
    snapshots = Latest()
    snapshots.publish([first])
    referred = []

    async def refer(url):
        invoker = _Invoker(url)
        referred.append(invoker)
        return invoker

    @asynccontextmanager
    async def changing():
        yield aiter(snapshots)

    class Failing(Router):
        def __init__(self):
            self.notified = 0

        def notify(self, invokers):
            self.notified += 1
            if self.notified > 1:
                raise ValueError("cannot take the providers")

        def route(self, invokers, invocation):
            return invokers

    directory = DynamicDirectory(changing, refer, "test.Greeter", [Failing()])
    with anyio.fail_after(5):
        await directory.__aenter__()
        snapshots.publish([second])
        await referred[0].closing.wait()
        with pytest.raises(ValueError, match="cannot take the providers"):
            await directory.aclose()

    assert [invoker.closed for invoker in referred] == [True, True]


async def test_cancelling_an_update_closes_each_invoker_it_already_created():
    first, second = URL.parse("tri://a:1/test.Greeter"), URL.parse("tri://b:1/test.Greeter")
    entering = anyio.Event()
    referred = []

    async def refer(url):
        if url == second:
            entering.set()
            await anyio.sleep_forever()
        invoker = _Invoker(url)
        referred.append(invoker)
        return invoker

    async def open_directory():
        async with DynamicDirectory(lambda: _fixed([first, second]), refer, "test.Greeter"):
            pytest.fail("the update finished before cancellation")

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(open_directory)
            await entering.wait()
            tasks.cancel_scope.cancel()

    assert [(invoker.url, invoker.closed) for invoker in referred] == [(first, True)]


async def test_ended_subscriptions_resume_without_recreating_unchanged_invokers(monkeypatch):
    monkeypatch.setattr("dubbo.utils.async_.backoff", lambda: itertools.repeat(0))
    first, second = URL.parse("tri://a:1/test.Greeter"), URL.parse("tri://b:1/test.Greeter")
    subscriptions = 0
    referred = []
    resumed = anyio.Event()

    @asynccontextmanager
    async def subscribe():
        nonlocal subscriptions
        subscriptions += 1

        async def snapshots():
            yield [first] if subscriptions == 1 else [first, second]
            if subscriptions > 1:
                resumed.set()
                await anyio.sleep_forever()

        yield snapshots()

    async def refer(url):
        invoker = _Invoker(url)
        referred.append(invoker)
        return invoker

    with anyio.fail_after(5):
        async with DynamicDirectory(subscribe, refer, "test.Greeter") as directory:
            await resumed.wait()
            assert directory.candidates(CALL) == tuple(referred)
            assert [invoker.url for invoker in referred] == [first, second]
            assert not any(invoker.closed for invoker in referred)

    assert subscriptions == 2


async def test_the_first_subscription_failure_reaches_the_caller_unchanged():
    failure = ConnectionError("unreachable")

    @asynccontextmanager
    async def subscribe():
        raise failure
        yield

    async def refer(url):
        return _Invoker(url)

    with pytest.raises(ConnectionError, match="unreachable") as caught:
        async with DynamicDirectory(subscribe, refer, "test.Greeter"):
            pass

    assert caught.value is failure
