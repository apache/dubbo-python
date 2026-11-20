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

import typing
import uuid
from collections.abc import Sequence
from typing import Any, Self
from urllib.parse import parse_qsl, urlencode

import anyio
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import Dubbo, Invocation, Invoker
from dubbo.cluster import Router
from dubbo.config import (
    ApplicationConfig,
    ConfigCenterConfig,
    ConsumerConfig,
    MetadataReportConfig,
    ProtocolConfig,
    ProviderConfig,
    ReferenceConfig,
    RegistryConfig,
    RegistryMode,
    ShutdownConfig,
)
from dubbo.extension import extensions
from dubbo.url import URL


@dubbo.service("test.registry.Greeter")
class _Greeter(typing.Protocol):
    @dubbo.method("Greet")
    async def greet(self, request: StringValue) -> StringValue: ...


@dubbo.service("test.registry.Echo")
class _Echo(typing.Protocol):
    @dubbo.method("Echo")
    async def echo(self, request: StringValue) -> StringValue: ...


class _EchoImpl(_Echo):
    async def echo(self, request: StringValue) -> StringValue:
        return request


class _GreeterImpl(_Greeter):
    def __init__(self, name: str = "a") -> None:
        self.name = name

    async def greet(self, request: StringValue) -> StringValue:
        return StringValue(value=f"{self.name}: hello {request.value}")


def _registry_config(address: str, **fields: Any) -> RegistryConfig:
    """Return the registry at ``address``, its ``group`` query parameter set as the field."""
    base, _, query = address.partition("?")
    parameters = dict(parse_qsl(query))
    group = parameters.pop("group", None)
    return RegistryConfig(address=base + (f"?{urlencode(parameters)}" if parameters else ""), group=group, **fields)


def _provider(
    address: str,
    mode: RegistryMode,
    *,
    name: str = "greeter-app",
    settings: ProviderConfig | None = None,
    shutdown: ShutdownConfig | None = None,
    config_center: ConfigCenterConfig | None = None,
    metadata_report: MetadataReportConfig | None = None,
    **application,
) -> Dubbo:
    return Dubbo(
        application=ApplicationConfig(name=name, **application),
        registries={"zk": _registry_config(address, mode=mode)},
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0)},
        provider=settings,
        shutdown=shutdown or ShutdownConfig(unregister_wait=0),
        config_center=config_center,
        metadata_report=metadata_report,
        env_prefix=None,
    )


def _config_center(address: str) -> ConfigCenterConfig:
    """Return the configuration center on the ZooKeeper of the registry at ``address``, under its root."""
    base, _, query = address.partition("?")
    parameters = dict(parse_qsl(query))
    client = f"?client={parameters['client']}" if "client" in parameters else ""
    return ConfigCenterConfig(address=base + client, namespace=parameters["group"], check=False)


def _consumer(address: str, mode: RegistryMode, **reference) -> Dubbo:
    return Dubbo(
        application=ApplicationConfig(name="caller-app"),
        registries={"zk": _registry_config(address, mode=mode)},
        consumer=ConsumerConfig(references={"test.registry.Greeter": ReferenceConfig(**reference)})
        if reference
        else None,
        env_prefix=None,
    )


@pytest.fixture(params=["memory", pytest.param("kazoo", marks=pytest.mark.zookeeper)])
async def registry_address(request, delete_tree, zk):
    root = f"test-{uuid.uuid4().hex}"
    if request.param == "memory":
        request.getfixturevalue("memory_zookeeper")
        yield f"zookeeper://127.0.0.1:2181?client=memory&group={root}"
    else:
        address = request.getfixturevalue("zookeeper")
        yield f"zookeeper://{address}?group={root}"
        async with zk(f"zookeeper://{address}") as client:
            await delete_tree(client, f"/{root}")


@pytest.fixture
async def real_registry_address(zookeeper, delete_tree, zk):
    root = f"test-{uuid.uuid4().hex}"
    yield f"zookeeper://{zookeeper}?group={root}"
    async with zk(f"zookeeper://{zookeeper}") as client:
        await delete_tree(client, f"/{root}")


class _ConsumerUpdates:
    def __init__(self):
        self.snapshots = []
        self.changed = anyio.Event()

    def publish(self, urls):
        self.snapshots.append(urls)
        self.changed.set()
        self.changed = anyio.Event()

    async def wait_for(self, predicate, *, since=0):
        with anyio.fail_after(5):
            while True:
                changed = self.changed
                for snapshot in self.snapshots[since:]:
                    if predicate(snapshot):
                        return snapshot
                await changed.wait()


@pytest.fixture
def consumer_updates(isolated_extensions) -> _ConsumerUpdates:
    """The providers of each reference whose routers include ``updates``, each time its directory takes them."""
    updates = _ConsumerUpdates()

    class Updates(Router):
        def __init__(self, url: URL) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def aclose(self) -> None:
            pass

        def notify(self, invokers: Sequence[Invoker]) -> None:
            updates.publish([invoker.url for invoker in invokers])

        def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
            return invokers

    extensions.register(Router, "updates", Updates)
    return updates


@pytest.fixture
def greeter_contract():
    return _Greeter


@pytest.fixture
def greeter_impl_type():
    return _GreeterImpl


@pytest.fixture
def echo_contract():
    return _Echo


@pytest.fixture
def echo_impl_type():
    return _EchoImpl


@pytest.fixture
def registry_config():
    return _registry_config


@pytest.fixture
def provider():
    return _provider


@pytest.fixture
def config_center():
    return _config_center


@pytest.fixture
def consumer():
    return _consumer
