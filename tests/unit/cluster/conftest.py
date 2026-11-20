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

from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager

import anyio
import attrs
import pytest

from dubbo import Invocation, Invoker, Method, Parameter, Result, RpcError, RpcType, Status
from dubbo.cluster import Cluster, StaticDirectory, create_cluster
from dubbo.url import URL


@attrs.define(kw_only=True)
class _Provider(Invoker):
    url: URL
    results: tuple[Result, ...]
    up: bool = True
    calls: int = 0
    closed: bool = False

    @property
    def available(self) -> bool:
        return self.up

    async def invoke(self, invocation: Invocation) -> Result:
        self.calls += 1

        return self.results[min(self.calls, len(self.results)) - 1]

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def provider():
    def create(host: str, *results: Result, query: str = "", port: int = 20880, up: bool = True):
        return _Provider(
            url=URL.parse(f"tri://127.0.0.1:{port}/test.Greeter?{query}").replace(host=host),
            results=results or (Result(value=host),),
            up=up,
        )

    return create


@pytest.fixture
def invocation():
    def create(method: str = "greet", *, arguments: tuple = (), **attachments: str) -> Invocation:
        return Invocation(
            interface="test.Greeter",
            method=method,
            definition=Method(name=method, request=(), response=None),
            arguments=arguments,
            attachments=attachments,
        )

    return create


@pytest.fixture
def call(invocation) -> Invocation:
    return invocation()


@pytest.fixture
def streaming_call() -> Invocation:
    method = Method(
        name="greet", rpc_type=RpcType.SERVER_STREAM, request=(Parameter(name="name", type=str),), response=str
    )

    return Invocation(interface="test.Greeter", method="greet", definition=method, arguments=("hi",))


@pytest.fixture
def unavailable() -> Result:
    return Result(error=RpcError(Status.UNAVAILABLE, "down"))


@pytest.fixture
def open_cluster():
    @asynccontextmanager
    async def open_(strategy: str, *providers: Invoker, query: str = "") -> AsyncIterator[Cluster]:
        url = URL.parse(f"consumer://127.0.0.1/test.Greeter?cluster={strategy}&loadbalance=roundrobin&{query}")
        with anyio.fail_after(5):
            async with aclosing(await create_cluster(url, StaticDirectory(providers))) as cluster:
                yield cluster

    return open_
