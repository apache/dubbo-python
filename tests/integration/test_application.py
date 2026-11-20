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
import errno
import socket
import typing
from contextlib import asynccontextmanager

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
import dubbo.application as application_module
from dubbo import Dubbo, DubboError, RpcError, Status
from dubbo.cluster import Router
from dubbo.config import ConsumerConfig, ProtocolConfig, ProviderConfig, ReferenceConfig, ShutdownConfig, TripleConfig
from dubbo.extension import extensions
from dubbo.filter import Filter
from dubbo.protocol.served import ServedExporter
from dubbo.rpc.invocation import Result

pytestmark = pytest.mark.anyio

APP = {"application": {"name": "orders"}}


@dubbo.service("com.example.UserService")
class UserService(typing.Protocol):
    @dubbo.method("getUser")
    async def get_user(self, id: StringValue) -> StringValue: ...


class UserServiceImpl(UserService):
    async def get_user(self, id: StringValue) -> StringValue:
        return StringValue(value="user " + id.value)


class Holding(UserService):
    """Answers with its prefix, holding the calls for the id ``hold`` until ``release`` is set."""

    def __init__(self, prefix: str, entered: anyio.Event, release: anyio.Event) -> None:
        self._prefix = prefix
        self._entered = entered
        self._release = release

    async def get_user(self, id: StringValue) -> StringValue:
        if id.value == "hold":
            self._entered.set()
            await self._release.wait()
        return StringValue(value=f"{self._prefix} {id.value}")


class Prefixed(UserService):
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    async def get_user(self, id: StringValue) -> StringValue:
        return StringValue(value=f"{self._prefix} {id.value}")


@dubbo.service("com.example.OrderService")
class OrderService(typing.Protocol):
    async def place(self, user: StringValue) -> StringValue: ...


def _protocols(**triple):
    return {"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0, triple=TripleConfig(**triple))}


@asynccontextmanager
async def _provider(exported_urls, implementation=None, **options):
    app = Dubbo(APP, protocols=_protocols(), env_prefix=None, **options)
    app.export(UserServiceImpl() if implementation is None else implementation)
    async with app:
        yield exported_urls[-1]


def _client(urls, **settings):
    reference = ReferenceConfig(urls=tuple(str(url) for url in urls), **settings)
    return Dubbo(APP, consumer=ConsumerConfig(references={"com.example.UserService": reference}), env_prefix=None)


async def test_a_reference_calls_the_service_of_its_group_in_another_application(exported_urls):
    async with _provider(exported_urls, provider=ProviderConfig(group="blue")) as url:
        client = _client([url.replace(parameters={})], group="blue")
        users = client.refer(UserService)

        async with client:
            assert await users.get_user(StringValue(value="2")) == StringValue(value="user 2")


async def test_a_reference_of_another_group_finds_no_such_service(exported_urls):
    async with _provider(exported_urls, provider=ProviderConfig(group="blue")) as url:
        client = _client([url.replace(parameters={})], group="red")
        users = client.refer(UserService)

        async with client:
            with pytest.raises(RpcError, match="UNIMPLEMENTED"):
                await users.get_user(StringValue(value="2"))


@pytest.fixture
def default_port_zero(monkeypatch):
    # The default Triple port is fixed; tests running at the same time each need their own.
    monkeypatch.setattr("dubbo.protocol.triple.protocol.DEFAULT_TRIPLE_PORT", 0)


async def test_exported_services_use_triple_when_no_protocol_is_configured(exported_urls, default_port_zero):
    app = Dubbo(APP, env_prefix=None)
    app.export(UserServiceImpl())

    async with app:
        assert app.config.protocols == {"tri": ProtocolConfig(name="tri")}
        (url,) = exported_urls
        async with await anyio.connect_tcp("127.0.0.1", url.port):
            pass


# Windows refuses the connection after its own retries, in real time.
@pytest.mark.real_clock
async def test_the_default_server_closes_when_the_application_stops(exported_urls, default_port_zero):
    app = Dubbo(APP, env_prefix=None)
    app.export(UserServiceImpl())

    async with app:
        (url,) = exported_urls

    with pytest.raises(OSError, match="connection attempts failed"):
        await anyio.connect_tcp("127.0.0.1", url.port)


async def test_the_exported_urls_tell_the_bound_ports_while_the_application_runs(default_port_zero):
    app = Dubbo(APP, env_prefix=None)
    app.export(UserServiceImpl())
    with pytest.raises(RuntimeError, match="while the application runs"):
        _ = app.exported_urls

    async with app:
        (url,) = app.exported_urls
        assert (url.path, url.port != 0) == ("com.example.UserService", True)
        async with await anyio.connect_tcp("127.0.0.1", url.port):
            pass

    with pytest.raises(RuntimeError, match="while the application runs"):
        _ = app.exported_urls


async def test_a_port_in_use_fails_the_start_with_an_os_error():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        app = Dubbo(APP, protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=port)}, env_prefix=None)
        app.export(UserServiceImpl())

        with pytest.raises(OSError, match=str(port)) as raised:
            async with app:
                pass

        assert raised.value.errno == errno.EADDRINUSE


async def test_an_application_without_services_exports_nothing(exported_urls, default_port_zero):
    async with Dubbo(APP, env_prefix=None):
        assert exported_urls == []


async def _filtered_calls(exported_urls, attempt_filters):
    """Return where the filters ``recording`` ran on a call retried once, with ``attempt_filters`` on each attempt, and the provider URL."""
    calls = []
    attempts = 0

    class Recording:
        def __init__(self, url):
            # A reference filter sees the reference, an attempt filter the provider it calls.
            self.side = f"tri:{url.port}" if url.protocol == "tri" else url.protocol

        async def invoke(self, call_next, invocation):
            calls.append((self.side, invocation.method))
            return await call_next(invocation)

    class BusyOnce:
        def __init__(self, url):
            pass

        async def invoke(self, call_next, invocation):
            nonlocal attempts
            attempts += 1
            calls.append(("service", invocation.method))
            if attempts == 1:
                return Result(error=RpcError(Status.UNAVAILABLE, "busy"))
            return await call_next(invocation)

    extensions.register(Filter, "recording", Recording)
    extensions.register(Filter, "busy-once", BusyOnce)

    async with _provider(exported_urls, provider=ProviderConfig(filters=("busy-once",))) as url:
        client = _client([url], retries=1, filters=("recording",), attempt_filters=attempt_filters)
        users = client.refer(UserService)

        async with client:
            assert await users.get_user(StringValue(value="1")) == StringValue(value="user 1")

    return calls, url


async def test_a_service_filter_that_raises_is_logged_and_its_caller_receives_internal(
    exported_urls, isolated_extensions, caplog
):
    class Broken:
        def __init__(self, url):
            pass

        async def invoke(self, call_next, invocation):
            raise RuntimeError("a bug in the filter")

    extensions.register(Filter, "broken", Broken)

    async with _provider(exported_urls, provider=ProviderConfig(filters=("broken",))) as url:
        client = _client([url], retries=0)
        users = client.refer(UserService)
        async with client:
            with pytest.raises(RpcError) as caught:
                await users.get_user(StringValue(value="1"))

    assert caught.value.status is Status.INTERNAL
    [record] = [record for record in caplog.records if "raised instead of returning a result" in record.getMessage()]
    assert (record.levelname, str(record.exc_info[1])) == ("ERROR", "a bug in the filter")


async def test_a_reference_filter_runs_once_around_a_call_and_a_service_filter_on_each_attempt(
    exported_urls, isolated_extensions
):
    calls, _ = await _filtered_calls(exported_urls, ())

    assert calls == [("consumer", "getUser"), ("service", "getUser"), ("service", "getUser")]


async def test_an_attempt_filter_runs_on_each_attempt_with_the_provider_it_calls(exported_urls, isolated_extensions):
    calls, url = await _filtered_calls(exported_urls, ("recording",))

    attempt, service = (f"tri:{url.port}", "getUser"), ("service", "getUser")
    assert calls == [("consumer", "getUser"), attempt, service, attempt, service]


async def test_a_reference_calls_only_the_providers_its_router_keeps(exported_urls, isolated_extensions):
    notified = []
    selected = []

    class KeepLast:
        def __init__(self, url):
            self.url = url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def aclose(self):
            pass

        def notify(self, invokers):
            notified.append(tuple(invoker.url.port for invoker in invokers))

        def route(self, invokers, invocation):
            selected.append(self.url.scope)
            return invokers[-1:]

    extensions.register(Router, "keep-last", KeepLast)

    async with (
        _provider(exported_urls, Prefixed("dropped")) as first,
        _provider(exported_urls, Prefixed("kept")) as second,
    ):
        client = _client([first, second], routers=("keep-last",))
        users = client.refer(UserService)

        async with client:
            assert await users.get_user(StringValue(value="1")) == StringValue(value="kept 1")

    assert notified == [(first.port, second.port)]
    assert len(selected) == 1


async def test_round_robin_configuration_alternates_between_providers(exported_urls):
    async with (
        _provider(exported_urls, Prefixed("first")) as first,
        _provider(exported_urls, Prefixed("second")) as second,
    ):
        client = _client([first, second], loadbalance="roundrobin")
        users = client.refer(UserService)

        async with client:
            answers = [(await users.get_user(StringValue(value="1"))).value for _ in range(4)]

    assert answers == ["first 1", "second 1"] * 2


@pytest.mark.parametrize("delay", [0, 0.05], ids=["at-once", "after-a-lifespan"])
async def test_a_reference_that_checks_fails_the_start_when_its_provider_refuses_whatever_the_timing(
    monkeypatch, delay
):
    monkeypatch.setattr(application_module, "_CHECK_GRACE", 0.5)

    @asynccontextmanager
    async def lifespan(app):
        await anyio.sleep(delay)
        yield

    # Nothing listens on port 1, so every attempt to connect is refused.
    client = Dubbo(
        APP,
        consumer=ConsumerConfig(references={"com.example.UserService": ReferenceConfig(urls=("tri://127.0.0.1:1",))}),
        lifespan=lifespan,
        env_prefix=None,
    )
    client.refer(UserService)

    with pytest.raises(RpcError, match=r"no provider of com\.example\.UserService is available"):
        async with client:
            pass


async def test_a_provider_whose_host_answers_no_connection_does_not_hold_up_calls(exported_urls):
    async with _provider(exported_urls, Prefixed("live")) as live:
        # A documentation address, which no network routes, stands for a provider whose host is gone. Its
        # connect timeout outlasts the calls, so that only an attempt the calls do not cancel can end.
        gone = live.replace(host="192.0.2.1", parameters={**live.parameters, "triple.connect-timeout": "400"})
        client = _client([gone, live], timeout=0.2)
        users = client.refer(UserService)

        async with client:
            # Both connect in the background from the start; the attempt to the gone one has failed by now.
            await anyio.sleep(0.6)
            with anyio.fail_after(5):
                answers = [(await users.get_user(StringValue(value="1"))).value for _ in range(10)]

    assert answers == ["live 1"] * 10


async def test_a_reference_of_a_tag_calls_only_the_providers_of_that_tag(exported_urls):
    async with (
        _provider(exported_urls, Prefixed("plain")) as plain,
        _provider(exported_urls, Prefixed("blue"), provider=ProviderConfig(tag="blue")) as blue,
    ):
        client = _client([plain, blue], loadbalance="roundrobin", tag="blue")
        users = client.refer(UserService)

        async with client:
            answers = [(await users.get_user(StringValue(value="1"))).value for _ in range(4)]

    assert answers == ["blue 1"] * 4


async def test_least_active_configuration_avoids_a_provider_with_an_inflight_call(exported_urls):
    entered, release = anyio.Event(), anyio.Event()
    async with (
        _provider(exported_urls, Holding("first", entered, release)) as first,
        _provider(exported_urls, Holding("second", entered, release)) as second,
    ):
        client = _client([first, second], loadbalance="leastactive")
        users = client.refer(UserService)
        held = []

        async def hold():
            held.append((await users.get_user(StringValue(value="hold"))).value)

        with anyio.fail_after(5):
            async with client, anyio.create_task_group() as tasks:
                tasks.start_soon(hold)
                await entered.wait()
                answers = [(await users.get_user(StringValue(value="1"))).value for _ in range(2)]
                release.set()

    prefix = "second" if held == ["first hold"] else "first"
    assert held in (["first hold"], ["second hold"])
    assert answers == [f"{prefix} 1"] * 2


# Windows refuses the connection after its own retries, in real time.
@pytest.mark.real_clock
async def test_export_failure_releases_the_servers_already_opened(exported_urls, isolated_extensions):
    from dubbo.transport.h2 import H2Server
    from dubbo.transport.h2.aio import AioH2Server

    class RefuseSecond(AioH2Server):
        async def __aenter__(self):
            if exported_urls:
                raise DubboError("cannot bind the second server") from OSError("address unavailable")
            return await super().__aenter__()

    extensions.register(H2Server, "refuse-second", RefuseSecond)
    protocols = {
        "first": ProtocolConfig(name="tri", host="127.0.0.1", port=0),
        "second": ProtocolConfig(
            name="tri", host="127.0.0.2", port=0, triple=TripleConfig(parameters={"server": "refuse-second"})
        ),
    }
    app = Dubbo(APP, protocols=protocols, env_prefix=None)
    app.export(UserServiceImpl())

    with pytest.raises(DubboError, match="cannot bind the second server") as caught:
        await app.__aenter__()

    assert isinstance(caught.value.__cause__, OSError)
    (url,) = exported_urls
    with pytest.raises(OSError, match="connection attempts failed"):
        await anyio.connect_tcp(url.host, url.port)


@dubbo.service("com.example.Echo")
class Echo(typing.Protocol):
    async def echo(self, text: str) -> str: ...


class EchoImpl(Echo):
    async def echo(self, text: str) -> str:
        return text


@pytest.fixture
def event_loop_told_in_tasks_only(monkeypatch):
    """Let AnyIO tell the event loop only inside a task, as it does where sniffio is installed."""

    def current_async_library() -> str | None:
        return "asyncio" if asyncio.current_task() is not None else None

    monkeypatch.setattr("anyio._core._eventloop.current_async_library", current_async_library)


@pytest.mark.parametrize("protocol", ["tri", "dubbo"])
async def test_servers_answer_where_anyio_tells_the_event_loop_only_inside_tasks(
    protocol, event_loop_told_in_tasks_only
):
    server = Dubbo(
        APP,
        protocols={protocol: ProtocolConfig(host="127.0.0.1", port=0)},
        provider=ProviderConfig(serialization="hessian2"),
        env_prefix=None,
    )
    server.export(EchoImpl())

    async with server:
        (url,) = (url for url in server.exported_urls if url.path == "com.example.Echo")
        client = Dubbo(APP, env_prefix=None)
        echo = client.refer(Echo, url=str(url))
        async with client:
            assert await echo.echo("hi") == "hi"


async def test_protocol_settings_limit_requests_on_the_server(exported_urls):
    app = Dubbo(APP, protocols=_protocols(max_receive_message_size=8), env_prefix=None)
    app.export(UserServiceImpl())

    async with app:
        client = _client([exported_urls[-1]])
        users = client.refer(UserService)
        async with client:
            assert await users.get_user(StringValue(value="1")) == StringValue(value="user 1")
            with pytest.raises(RpcError, match="RESOURCE_EXHAUSTED"):
                await users.get_user(StringValue(value="x" * 32))


def _limited_client(url, query_limit, consumer_limit, reference_limit):
    parameters = {"triple.max-receive-message-size": str(query_limit)} if query_limit else {}
    reference = ReferenceConfig(
        urls=(str(url.replace(parameters=parameters)),),
        triple=TripleConfig(max_receive_message_size=reference_limit),
    )
    return Dubbo(
        APP,
        consumer=ConsumerConfig(
            triple=TripleConfig(max_receive_message_size=consumer_limit),
            references={"com.example.UserService": reference},
        ),
        env_prefix=None,
    )


@pytest.mark.parametrize(("query_limit", "consumer_limit"), [(8, None), (None, 8)], ids=["query", "consumer"])
async def test_a_receive_limit_of_the_url_or_the_consumer_refuses_a_larger_response(
    exported_urls, query_limit, consumer_limit
):
    async with _provider(exported_urls) as url:
        client = _limited_client(url, query_limit, consumer_limit, None)
        users = client.refer(UserService)

        async with client:
            with pytest.raises(RpcError, match="RESOURCE_EXHAUSTED"):
                await users.get_user(StringValue(value="x" * 32))


@pytest.mark.parametrize(("query_limit", "consumer_limit"), [(8, None), (None, 8)], ids=["over-query", "over-consumer"])
async def test_the_receive_limit_of_a_reference_overrides_those_of_the_url_and_the_consumer(
    exported_urls, query_limit, consumer_limit
):
    async with _provider(exported_urls) as url:
        client = _limited_client(url, query_limit, consumer_limit, 1024)
        users = client.refer(UserService)

        async with client:
            assert await users.get_user(StringValue(value="x" * 32)) == StringValue(value="user " + "x" * 32)


async def test_configured_timeouts_end_a_unary_call(exported_urls):
    release = anyio.Event()

    class Slow(UserService):
        async def get_user(self, id):
            await release.wait()
            return id

    async with _provider(exported_urls, Slow()) as url:
        client = _client([url], timeout=0.05)
        users = client.refer(UserService)
        async with client:
            with anyio.fail_after(5), pytest.raises(RpcError, match="DEADLINE_EXCEEDED"):
                await users.get_user(StringValue(value="1"))
            release.set()


async def test_stopping_services_can_finish_calls_using_their_application_references(exported_urls, monkeypatch):
    entered, release, closing = anyio.Event(), anyio.Event(), anyio.Event()
    close = ServedExporter.aclose

    async def observe(exporter):
        closing.set()
        await close(exporter)

    monkeypatch.setattr(ServedExporter, "aclose", observe)
    async with _provider(exported_urls) as users_url:

        class Orders(OrderService):
            async def place(self, user):
                entered.set()
                await release.wait()
                found = await users.get_user(user)
                return StringValue(value="order for " + found.value)

        orders_app = Dubbo(
            APP,
            protocols=_protocols(),
            consumer=ConsumerConfig(references={"com.example.UserService": ReferenceConfig(urls=(str(users_url),))}),
            env_prefix=None,
        )
        users = orders_app.refer(UserService)
        orders_app.export(Orders())
        ready, stop, answered = anyio.Event(), anyio.Event(), anyio.Event()
        answers = []

        async def serve():
            async with orders_app:
                ready.set()
                await stop.wait()

        async def place(orders):
            answers.append(await orders.place(StringValue(value="3")))
            answered.set()

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(serve)
                await ready.wait()
                orders_url = exported_urls[-1]
                client = Dubbo(APP, env_prefix=None)
                orders = client.refer(OrderService, url=str(orders_url))
                async with client:
                    tasks.start_soon(place, orders)
                    await entered.wait()
                    stop.set()
                    await closing.wait()
                    release.set()
                    await answered.wait()

        assert answers == [StringValue(value="order for user 3")]


async def test_cancelling_an_application_cancels_its_running_calls(exported_urls):
    entered = anyio.Event()

    class Orders(OrderService):
        async def place(self, user):
            entered.set()
            await anyio.sleep_forever()

    app = Dubbo(APP, protocols=_protocols(), env_prefix=None)
    app.export(Orders())
    ready, stop, cancelled = anyio.Event(), anyio.Event(), anyio.Event()

    async def serve():
        with anyio.CancelScope() as owner:
            async with app:
                ready.set()
                await stop.wait()
                owner.cancel()
                await anyio.sleep_forever()

    async def place(orders):
        with pytest.raises(RpcError, match="CANCELLED: the HTTP/2 stream"):
            await orders.place(StringValue(value="3"))
        cancelled.set()

    with anyio.fail_after(2):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(serve)
            await ready.wait()
            client = Dubbo(APP, env_prefix=None)
            orders = client.refer(OrderService, url=str(exported_urls[-1]))
            async with client:
                tasks.start_soon(place, orders)
                await entered.wait()
                stop.set()
                await cancelled.wait()


async def test_the_lifespan_holds_what_the_services_use_from_before_they_serve_until_they_drain(exported_urls):
    state, entered, release = {"resource": "none", "served": None}, anyio.Event(), anyio.Event()

    @asynccontextmanager
    async def lifespan(app):
        state["served"] = list(exported_urls)
        state["resource"] = "open"
        yield
        state["resource"] = "closed"

    class Users(UserService):
        async def get_user(self, id):
            entered.set()
            await release.wait()
            return StringValue(value=state["resource"])

    app = Dubbo(APP, protocols=_protocols(), lifespan=lifespan, env_prefix=None)
    app.export(Users())
    ready, stop = anyio.Event(), anyio.Event()
    answers = []

    async def serve():
        async with app:
            ready.set()
            await stop.wait()

    async def call(users):
        answers.append((await users.get_user(StringValue(value="1"))).value)

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(serve)
            await ready.wait()
            client = Dubbo(APP, env_prefix=None)
            users = client.refer(UserService, url=str(exported_urls[-1]))
            async with client, anyio.create_task_group() as calls:
                calls.start_soon(call, users)
                await entered.wait()
                stop.set()
                await anyio.wait_all_tasks_blocked()
                release.set()

    assert state["served"] == []
    assert answers == ["open"]
    assert state["resource"] == "closed"


async def test_cancelling_the_task_of_an_application_with_asyncio_stops_it_at_once(exported_urls):
    entered = anyio.Event()

    class Orders(OrderService):
        async def place(self, user):
            entered.set()
            await anyio.sleep_forever()

    app = Dubbo(APP, protocols=_protocols(), shutdown=ShutdownConfig(grace=30), env_prefix=None)
    app.export(Orders())
    ready = anyio.Event()

    async def serve():
        async with app:
            ready.set()
            await anyio.sleep_forever()

    async def place(orders):
        with pytest.raises(RpcError, match="CANCELLED"):
            await orders.place(StringValue(value="3"))

    with anyio.fail_after(2):
        serving = asyncio.create_task(serve())
        await ready.wait()
        client = Dubbo(APP, env_prefix=None)
        orders = client.refer(OrderService, url=str(exported_urls[-1]))
        async with client, anyio.create_task_group() as tasks:
            tasks.start_soon(place, orders)
            await entered.wait()
            serving.cancel()
            with pytest.raises(asyncio.CancelledError):
                await serving


def _generic_client():
    reference = ReferenceConfig(methods={"anyMethod": dubbo.config.MethodConfig(timeout=1)})
    return Dubbo(APP, consumer=ConsumerConfig(references={"com.example.UserService": reference}), env_prefix=None)


async def test_a_generic_reference_sends_invoke_calls_to_its_provider(exported_urls):
    async with _provider(exported_urls) as url:
        client = _generic_client()
        generic = client.refer_generic("com.example.UserService", url=str(url))

        async with client:
            with pytest.raises(RpcError, match="UNIMPLEMENTED") as caught:
                await generic.call("getUser", {"value": "x"})

    assert "/com.example.UserService/$invoke" in caught.value.message


async def test_a_generic_reference_beside_a_reference_with_the_contract_leaves_its_calls_as_they_are(exported_urls):
    async with _provider(exported_urls) as url:
        client = _generic_client()
        users = client.refer(UserService, url=str(url))
        generic = client.refer_generic("com.example.UserService", url=str(url))

        async with client:
            assert await users.get_user(StringValue(value="x")) == StringValue(value="user x")
            with pytest.raises(RpcError, match="UNIMPLEMENTED") as caught:
                await generic.call("getUser", {"value": "x"})

    assert "/com.example.UserService/$invoke" in caught.value.message


async def test_an_unconfigured_application_calls_the_url_given_in_code(exported_urls):
    async with _provider(exported_urls) as url:
        client = Dubbo(env_prefix=None)
        users = client.refer(UserService, url=str(url))

        async with client:
            assert await users.get_user(StringValue(value="x")) == StringValue(value="user x")
