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
import typing
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import Dubbo
from dubbo.config import (
    ApplicationConfig,
    ConfigError,
    ConfigReadError,
    ConsumerConfig,
    MethodConfig,
    ProtocolConfig,
    ProviderConfig,
    ReferenceConfig,
    ServiceConfig,
)
from dubbo.extension import ExtensionError, extensions
from dubbo.protocol import Exporter, Protocol
from dubbo.rpc.context import serving
from dubbo.rpc.invocation import Invoker

pytestmark = pytest.mark.anyio
APP = {"application": {"name": "orders"}}


async def test_default_env_prefix_reads_dubbo_variables(monkeypatch):
    monkeypatch.setenv("DUBBO__APPLICATION__NAME", "from-env")
    async with Dubbo() as app:
        assert app.config.application.name == "from-env"


async def test_configuration_exists_only_after_start():
    app = Dubbo(APP, env_prefix=None)
    with pytest.raises(RuntimeError, match="once the application has started"):
        _ = app.config
    async with app:
        assert app.config.application.name == "orders"
        with pytest.raises(RuntimeError, match="already"):
            await app.__aenter__()


async def test_sources_are_read_at_start_and_left_unmodified(tmp_path):
    source = {"application": {"name": "orders"}}
    path = tmp_path / "later.json"
    app = Dubbo(source, path, env_prefix=None)
    path.write_text('{"application": {"version": "1"}}', encoding="utf-8")

    async with app:
        assert app.config.application == ApplicationConfig(name="orders", version="1")

    assert source == {"application": {"name": "orders"}}


async def test_an_unreadable_source_reports_the_path_and_original_error(tmp_path):
    app = Dubbo(tmp_path / "missing.json", env_prefix=None)

    with pytest.raises(ConfigReadError, match=r"missing\.json") as caught:
        await app.__aenter__()

    assert isinstance(caught.value.__cause__, FileNotFoundError)


@dubbo.service("com.example.UserService")
class UserService(typing.Protocol):
    @dubbo.method("getUser")
    async def get_user(self, id: StringValue) -> StringValue: ...


class UserServiceImpl(UserService):
    async def get_user(self, id: StringValue) -> StringValue:
        return StringValue(value="user " + id.value)


def test_a_service_is_exported_once():
    app = Dubbo(APP, env_prefix=None)
    app.export(UserServiceImpl())

    with pytest.raises(ValueError, match="already exported"):
        app.export(UserServiceImpl())


def test_only_an_implementation_of_a_service_contract_is_exported():
    app = Dubbo(APP, env_prefix=None)

    with pytest.raises(TypeError, match="does not implement a service contract"):
        app.export(object())


async def test_services_are_exported_and_referenced_only_before_start(memory_protocol):
    app = Dubbo(APP, env_prefix=None, protocols={"memory": ProtocolConfig(name="memory")})
    app.export(UserServiceImpl())
    app.refer(UserService, url="memory://local:1")

    async with app:
        with pytest.raises(RuntimeError, match="cannot export once the application has started"):
            app.export(UserServiceImpl())
        with pytest.raises(RuntimeError, match="cannot refer once the application has started"):
            app.refer(UserService)


async def test_a_reference_calls_only_while_its_application_runs(memory_protocol):
    app = Dubbo(APP, env_prefix=None, protocols={"memory": ProtocolConfig(name="memory")})
    app.export(UserServiceImpl())
    users = app.refer(UserService, url="memory://local:1")

    async with app:
        assert await users.get_user(StringValue(value="7")) == StringValue(value="user 7")

    with pytest.raises(RuntimeError, match=r"com\.example\.UserService is called only while the application runs"):
        await users.get_user(StringValue(value="1"))


@pytest.mark.parametrize(
    "options",
    [{"provider": ProviderConfig(filters=("nope",))}, {"consumer": ConsumerConfig(filters=("nope",))}],
    ids=["service", "reference"],
)
async def test_a_filter_that_is_not_installed_fails_startup(options, memory_protocol):
    app = Dubbo(APP, env_prefix=None, protocols={"memory": ProtocolConfig(name="memory")}, **options)
    app.export(UserServiceImpl())
    app.refer(UserService, url="memory://local:1")

    with pytest.raises(ExtensionError, match=r"unknown extension 'nope' in group 'apache_dubbo\.filter'"):
        await app.__aenter__()


async def test_a_reference_needs_a_url():
    app = Dubbo(APP, env_prefix=None)
    app.refer(UserService)

    with pytest.raises(ConfigError, match=r"reference 'com\.example\.UserService' needs urls"):
        await app.__aenter__()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            {"consumer": ConsumerConfig(references={"com.example.UserService": ReferenceConfig(urls=("trii://h:1",))})},
            r"unknown extension 'trii' in group 'apache_dubbo\.protocol'; installed: .*tri",
        ),
        (
            {"protocols": {"main": ProtocolConfig(name="grpc", port=0)}},
            r"unknown extension 'grpc' in group 'apache_dubbo\.protocol'",
        ),
    ],
    ids=["reference", "protocol"],
)
async def test_an_unknown_protocol_fails_to_start(options, message):
    app = Dubbo(APP, env_prefix=None, **options)
    if "consumer" in options:
        app.refer(UserService)
    else:
        app.export(UserServiceImpl())

    with pytest.raises(ExtensionError, match=message):
        await app.__aenter__()


@pytest.mark.parametrize("setting", ["cluster", "loadbalance"])
async def test_a_reference_does_not_start_with_an_extension_not_installed(setting, memory_protocol):
    app = Dubbo(
        APP,
        env_prefix=None,
        consumer=ConsumerConfig(
            references={"com.example.UserService": ReferenceConfig(urls=("memory://local:1",), **{setting: "nope"})}
        ),
    )
    app.refer(UserService)

    with pytest.raises(ExtensionError, match=f"unknown extension 'nope' in group 'apache_dubbo.{setting}'"):
        async with app:
            pass


@asynccontextmanager
async def _stuck_stopping(app: Dubbo) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await anyio.sleep_forever()


async def test_leaving_stops_within_the_grace_in_all():
    app = Dubbo({**APP, "shutdown": {"grace": 0.1}}, lifespan=_stuck_stopping, env_prefix=None)

    with anyio.fail_after(2):
        async with app:
            pass


async def test_stopping_past_the_grace_after_an_error_raises_the_error():
    app = Dubbo({**APP, "shutdown": {"grace": 0.1}}, lifespan=_stuck_stopping, env_prefix=None)

    async def run() -> None:
        async with app:
            raise ValueError("the body failed")

    with anyio.fail_after(2), pytest.raises(ValueError, match="the body failed"):
        await run()


async def test_a_failed_start_closes_within_the_configured_grace(isolated_extensions):
    class Stuck(Invoker):
        def __init__(self, url):
            self._url = url

        @property
        def url(self):
            return self._url

        async def invoke(self, invocation):
            raise NotImplementedError

        async def aclose(self):
            await anyio.sleep_forever()

    class SecondFails(Protocol):
        def __init__(self):
            self.referred = 0

        async def refer(self, url, definition):
            self.referred += 1
            if self.referred == 2:
                raise RuntimeError("the second reference failed")
            return Stuck(url)

        async def aclose(self):
            pass

    extensions.register(Protocol, "stuck", SecondFails)
    app = Dubbo({**APP, "shutdown": {"grace": 0.1}, "consumer": {"routers": []}}, env_prefix=None)
    app.refer_generic("com.example.First", url="stuck://127.0.0.1:1")
    app.refer_generic("com.example.Second", url="stuck://127.0.0.1:1")

    with anyio.fail_after(2), pytest.raises(RuntimeError, match="the second reference failed"):
        async with app:
            pass


async def test_another_contract_cannot_refer_to_the_same_service():
    @dubbo.service("com.example.UserService")
    class OtherUserService(typing.Protocol):
        async def get_user(self, id: int) -> str: ...

    app = Dubbo(APP, env_prefix=None)
    app.refer(UserService)

    with pytest.raises(ValueError, match=r"another contract already refers to com\.example\.UserService"):
        app.refer(OtherUserService)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            {
                "provider": ProviderConfig(
                    services={"com.example.UserService": ServiceConfig(methods={"get_user": MethodConfig(timeout=1)})}
                )
            },
            "service 'com.example.UserService' configures methods it does not have: get_user",
        ),
        (
            {
                "consumer": ConsumerConfig(
                    references={"com.example.UserService": ReferenceConfig(methods={"nope": MethodConfig()})}
                )
            },
            "reference 'com.example.UserService' configures methods it does not have: nope",
        ),
    ],
    ids=["service", "reference"],
)
async def test_start_checks_method_settings_against_the_contract(options, message):
    # Methods are configured by the names they have on the wire.
    app = Dubbo(APP, env_prefix=None, **options)
    app.export(UserServiceImpl())
    app.refer(UserService)

    with pytest.raises(ConfigError, match=message):
        await app.__aenter__()


def test_invalid_source_type_fails_at_construction():
    with pytest.raises(TypeError, match="path or a mapping"):
        Dubbo([("application", {})])


async def test_the_lifespan_runs_while_the_application_runs():
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: Dubbo) -> AsyncIterator[None]:
        events.append(f"start {app.config.application.name}")
        yield
        events.append("stop")

    async with Dubbo({"application": {"name": "orders"}}, lifespan=lifespan, env_prefix=None):
        assert events == ["start orders"]

    assert events == ["start orders", "stop"]


async def test_a_lifespan_that_fails_to_start_fails_startup():
    @asynccontextmanager
    async def lifespan(app: Dubbo) -> AsyncIterator[None]:
        raise RuntimeError("no database")
        yield

    app = Dubbo({"application": {"name": "orders"}}, lifespan=lifespan, env_prefix=None)

    with pytest.raises(RuntimeError, match="no database"):
        await app.__aenter__()
    with pytest.raises(RuntimeError, match="once the application has started"):
        _ = app.config


async def test_serve_forever_needs_a_started_application():
    with pytest.raises(RuntimeError, match="once it has started"):
        await Dubbo(APP, env_prefix=None).serve_forever()


def test_a_reference_takes_one_url_in_code_and_does_not_show_the_other():
    app = Dubbo(env_prefix=None)
    app.refer(UserService, url="tri://alice:secret@127.0.0.1:1")

    with pytest.raises(ValueError, match="already referred to at another url") as caught:
        app.refer(UserService, url="tri://127.0.0.1:2")
    assert "secret" not in str(caught.value)


async def test_a_starting_application_refuses_to_start_again_or_to_refer():
    starting, proceed = anyio.Event(), anyio.Event()

    @asynccontextmanager
    async def lifespan(app: Dubbo) -> AsyncIterator[None]:
        starting.set()
        await proceed.wait()
        yield

    app = Dubbo(APP, lifespan=lifespan, env_prefix=None)

    async def run() -> None:
        async with app:
            pass

    with anyio.fail_after(5):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run)
            await starting.wait()

            with pytest.raises(RuntimeError, match="already started"):
                await app.__aenter__()
            with pytest.raises(RuntimeError, match="once the application has started"):
                app.refer(UserService)
            proceed.set()


class _Reference(Invoker):
    def __init__(self, protocol, url):
        self.protocol, self._url = protocol, url

    @property
    def url(self):
        return self._url

    async def invoke(self, invocation):
        with serving(invocation.attachments, peer=None):
            return await self.protocol.services[self.url.path].invoke(invocation)

    async def aclose(self):
        pass


class _Exporter(Exporter):
    def __init__(self, url, services):
        self._url, self.services = url, services

    @property
    def url(self):
        return self._url

    async def aclose(self):
        self.services.pop(self.url.path)


class _Protocol(Protocol):
    def __init__(self):
        self.services = {}

    async def export(self, url, definition, invoker):
        self.services[definition.interface] = invoker
        return _Exporter(url, self.services)

    async def refer(self, url, definition):
        return _Reference(self, url)

    async def aclose(self):
        pass


@pytest.fixture
def memory_protocol(isolated_extensions):
    extensions.register(Protocol, "memory", _Protocol)


@pytest.mark.parametrize(
    ("interface", "options", "message"),
    [
        ("com.example.UserService", {"url": "tri://other:2"}, "already referred to at another url"),
        ("com.example.UserService", {"generic": "gson"}, "already referred to with generic=true"),
        ("", {}, "interface must not be empty"),
    ],
    ids=["conflicting-url", "conflicting-form", "empty-interface"],
)
def test_generic_references_reject_conflicting_or_empty_identity(interface, options, message):
    app = Dubbo(env_prefix=None)
    app.refer_generic("com.example.UserService", url="tri://local:1")

    with pytest.raises(ValueError, match=message):
        app.refer_generic(interface, **options)


CENTER = {"application": {"name": "orders"}, "config_center": {"address": "memory://center"}}


async def test_connection_stays_open_until_the_application_stops(config_store):
    app = Dubbo(CENTER, env_prefix=None)

    async with app:
        (center,) = config_store.centers
        assert (center.connected, center.closed) == (True, False)

    assert center.closed


async def test_unchecked_center_failure_starts_with_local_configuration(config_store, caplog):
    config_store.error = ConnectionRefusedError("refused")
    center = {"address": "memory://user:secret@center", "check": False}
    app = Dubbo(CENTER, {"consumer": {"retries": 1}, "config_center": center}, env_prefix=None)

    with caplog.at_level(logging.WARNING, logger="dubbo"):
        async with app:
            assert app.config.consumer.retries == 1
            # The connection itself works, so it stays open for later readers.
            assert (config_store.centers[0].connected, config_store.centers[0].closed) == (True, False)

    assert config_store.centers[0].closed

    # The URL in the warning hides the password.
    assert "Starting without configuration center memory://user:***@center" in caplog.text
    assert "secret" not in caplog.text


USERS = "com.example.UserService"


async def test_export_and_refer_take_settings_above_those_of_the_sources(memory_protocol):
    source = {
        **APP,
        "provider": {"services": {USERS: {"weight": 10, "timeout": 2}}},
        "consumer": {"references": {USERS: {"retries": 7, "timeout": 2}}},
    }
    app = Dubbo(source, env_prefix=None, protocols={"memory": ProtocolConfig(name="memory")})
    app.export(UserServiceImpl(), config=ServiceConfig(weight=50))
    users = app.refer(UserService, url="memory://local:1", config=ReferenceConfig(retries=5))

    async with app:
        service, reference = app.config.provider.services[USERS], app.config.consumer.references[USERS]
        assert (service.weight, service.timeout) == (50, 2)
        assert (reference.retries, reference.timeout, reference.urls) == (5, 2, ("memory://local:1",))
        assert await users.get_user(StringValue(value="7")) == StringValue(value="user 7")


def test_a_service_given_settings_by_the_provider_argument_takes_no_others_from_export():
    app = Dubbo(env_prefix=None, provider=ProviderConfig(services={USERS: ServiceConfig(weight=10)}))

    with pytest.raises(ValueError, match=r"com\.example\.UserService is already configured in provider\.services"):
        app.export(UserServiceImpl(), config=ServiceConfig(weight=50))


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [
        ({"config": ReferenceConfig(retries=5)}, {"config": ReferenceConfig(retries=6)}, "with other settings"),
        ({}, {"url": "tri://a:1", "config": ReferenceConfig(urls=("tri://b:1",))}, "name different providers"),
        ({"url": "tri://a:1"}, {"config": ReferenceConfig(urls=("tri://b:1",))}, "name different providers"),
        (
            {"config": ReferenceConfig(urls=("tri://a:1", "tri://b:1"))},
            {"url": "tri://a:1"},
            "name different providers",
        ),
    ],
    ids=["other-settings", "url-and-urls", "url-then-urls", "urls-then-url"],
)
def test_a_reference_takes_one_set_of_settings_whose_urls_agree_with_its_url(first, second, message):
    app = Dubbo(env_prefix=None)
    app.refer(UserService, **first)

    with pytest.raises(ValueError, match=message):
        app.refer_generic(USERS, **second)


def test_a_reference_given_settings_by_the_consumer_argument_takes_no_others_from_refer():
    app = Dubbo(env_prefix=None, consumer=ConsumerConfig(references={USERS: ReferenceConfig(retries=1)}))

    with pytest.raises(ValueError, match=r"com\.example\.UserService is already configured in consumer\.references"):
        app.refer(UserService, config=ReferenceConfig(retries=5))


def test_a_reference_may_repeat_its_settings_and_the_url_they_name():
    config = ReferenceConfig(urls=("tri://a:1",), retries=5)
    app = Dubbo(env_prefix=None)
    app.refer(UserService, url="tri://a:1", config=config)

    app.refer(UserService, config=config)
    app.refer_generic(USERS, url="tri://a:1", config=ReferenceConfig(urls=("tri://a:1",), retries=5))
