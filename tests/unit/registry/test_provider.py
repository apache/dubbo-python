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

import math
from contextlib import asynccontextmanager
from importlib.metadata import version

import anyio
import pytest
from anyio.lowlevel import checkpoint

from dubbo.config import ApplicationConfig, DubboConfig, ShutdownConfig
from dubbo.extension import ApplicationScope, extensions
from dubbo.protocol.exported import ExportedService
from dubbo.registry import InterfaceRegistry
from dubbo.registry.provider import (
    _InterfaceRegistration,
    _Kept,
    _register_on_change,
    register_services,
)
from dubbo.rpc.definition import Method, Service
from dubbo.url import ADVERTISED_PORT, APPLICATION_SCOPE, CONFIG_CENTER_URL, URL
from dubbo.utils import Latest

pytestmark = pytest.mark.anyio


class _Registry(InterfaceRegistry):
    def __init__(self, url, registered, removed):
        super().__init__(url)
        self.registered, self.removed = registered, removed

    @asynccontextmanager
    async def register(self, url):
        self.registered.append(url)
        try:
            yield
        finally:
            self.removed.append(url)

    async def aclose(self):
        pass

    async def __aenter__(self):
        return self


async def test_a_change_of_the_rules_applies_while_registering_an_earlier_one_still_fails() -> None:
    changes: Latest[None] = Latest()
    rules, applied, attempted = ["first"], [], []
    send, receive = anyio.create_memory_object_stream[None](math.inf)

    async def register() -> None:
        attempted.append(rules[0])
        send.send_nowait(None)
        await checkpoint()
        raise ConnectionError("the registry is down")

    with anyio.fail_after(5):
        async with send, receive, anyio.create_task_group() as task_group:
            task_group.start_soon(_register_on_change, changes, lambda: applied.append(rules[0]), register)
            changes.publish(None)
            await receive.receive()
            rules[0] = "second"
            changes.publish(None)
            await receive.receive()
            task_group.cancel_scope.cancel()

    assert applied == ["first", "second"]
    assert attempted == ["first", "second"]


async def test_simplification_keeps_an_overridden_interface_extra_keys_and_declared_method_prefixes(config_store):
    registered, removed = [], []

    extensions.register(InterfaceRegistry, "recording", lambda url: _Registry(url, registered, removed))
    config_store.put(
        "demo.configurators",
        """scope: application
key: demo
configs:
  - side: provider
    parameters:
      interface: test.Greeter
      Greet.timeout: 500
      Greeting.timeout: 700
      custom: x
""",
    )
    config = DubboConfig(application=ApplicationConfig(name="demo"), shutdown=ShutdownConfig(unregister_wait=0))
    definition = Service(
        interface="greeter", methods=[Method(name=name, request=(), response=None) for name in ("Greet", "Farewell")]
    )

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            attributes = {APPLICATION_SCOPE: scope}
            center = URL.parse("memory://rules").replace(attributes=attributes)
            served = URL.parse("tri://10.0.0.5:50051/greeter?application=demo").replace(
                attributes=attributes | {CONFIG_CENTER_URL: center}
            )
            registry = URL.parse(
                "recording://registry?register-mode=interface&simplified=true&extra-keys=custom"
            ).replace(attributes=attributes)
            exported = ExportedService(
                interface="greeter",
                definition=definition,
                url=served,
                reconfigure=lambda changes: None,
                registries=[registry],
            )

            async with register_services(config, [exported], scope):
                assert registered == [
                    URL(
                        protocol="tri",
                        host="10.0.0.5",
                        port=50051,
                        path="greeter",
                        parameters={
                            "application": "demo",
                            "dubbo": "2.0.2",
                            "release": version("apache-dubbo"),
                            "side": "provider",
                            "interface": "test.Greeter",
                            "Greet.timeout": "500",
                            "custom": "x",
                        },
                    )
                ]

    assert removed == registered


@pytest.mark.parametrize("simplified", ["false", "true"])
async def test_a_registry_publishes_the_parameters_of_a_service_its_extra_keys_name(isolated_extensions, simplified):
    registered, removed = [], []

    extensions.register(InterfaceRegistry, "recording", lambda url: _Registry(url, registered, removed))
    config = DubboConfig(application=ApplicationConfig(name="demo"), shutdown=ShutdownConfig(unregister_wait=0))
    definition = Service(interface="greeter", methods=[Method(name="Greet", request=(), response=None)])

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            attributes = {APPLICATION_SCOPE: scope}
            served = URL.parse("tri://10.0.0.5:50051/greeter?application=demo&env=gray&threads=9").replace(
                attributes=attributes
            )
            registry = URL.parse(
                f"recording://registry?register-mode=interface&simplified={simplified}&extra-keys=env"
            ).replace(attributes=attributes)
            exported = ExportedService(
                interface="greeter",
                definition=definition,
                url=served,
                reconfigure=lambda changes: None,
                registries=[registry],
            )

            async with register_services(config, [exported], scope):
                [url] = registered
                assert url.parameters["env"] == "gray"
                assert "threads" not in url.parameters


@pytest.mark.parametrize(("advertised", "expected"), [({ADVERTISED_PORT: 30051}, 30051), ({}, 50051)])
async def test_a_service_is_registered_with_the_advertised_port_of_its_protocol(
    isolated_extensions, advertised, expected
):
    registered, removed = [], []

    extensions.register(InterfaceRegistry, "recording", lambda url: _Registry(url, registered, removed))
    config = DubboConfig(application=ApplicationConfig(name="demo"), shutdown=ShutdownConfig(unregister_wait=0))
    definition = Service(interface="greeter", methods=[Method(name="Greet", request=(), response=None)])

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            attributes = {APPLICATION_SCOPE: scope}
            served = URL.parse("tri://10.0.0.5:50051/greeter?application=demo").replace(
                attributes=attributes | advertised
            )
            registry = URL.parse("recording://registry?register-mode=interface").replace(attributes=attributes)
            exported = ExportedService(
                interface="greeter",
                definition=definition,
                url=served,
                reconfigure=lambda changes: None,
                registries=[registry],
            )

            async with register_services(config, [exported], scope):
                [url] = registered
                assert (url.host, url.port) == ("10.0.0.5", expected)


async def test_a_url_whose_registration_failed_is_registered_again_next_time():
    registered, removed = [], []
    failures = [ConnectionError("the registry is down")]

    class Flaky(_Registry):
        @asynccontextmanager
        async def register(self, url):
            if failures:
                raise failures.pop()
            async with super().register(url):
                yield

    first, second = URL.parse("tri://10.0.0.5:1/greeter?weight=1"), URL.parse("tri://10.0.0.5:1/greeter?weight=2")
    async with anyio.create_task_group() as task_group:
        registration = _InterfaceRegistration(
            registry=URL.parse("memory://registry"), client=Flaky(None, registered, removed), kept=_Kept(task_group)
        )

        with pytest.raises(ConnectionError):
            await registration.register([first])
        await registration.register([first])
        await registration.register([second])
        await registration.unregister()

    assert (registered, removed) == ([first, second], [first, second])


async def test_a_registration_is_entered_and_exited_in_one_task_whichever_task_registers_and_releases():
    tasks: list[tuple[str, int]] = []

    class Recording(_Registry):
        @asynccontextmanager
        async def register(self, url):
            tasks.append(("enter", anyio.get_current_task().id))
            yield
            tasks.append(("exit", anyio.get_current_task().id))

    url = URL.parse("tri://10.0.0.5:1/greeter")
    async with anyio.create_task_group() as task_group:
        registration = _InterfaceRegistration(
            registry=URL.parse("memory://registry"), client=Recording(None, [], []), kept=_Kept(task_group)
        )
        async with anyio.create_task_group() as registering:
            registering.start_soon(registration.register, [url])
        await registration.unregister()

    [(_, entered), (_, exited)] = tasks
    assert entered == exited
    assert entered != anyio.get_current_task().id
