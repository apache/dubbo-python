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
import attrs
import pytest

from dubbo import Invocation, Invoker, Method, Result
from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, URL


@attrs.define(kw_only=True)
class _Ending(Invoker):
    result: Result
    url: URL
    calls: list[Invocation] = attrs.field(factory=list)
    closed: bool = False

    async def invoke(self, invocation: Invocation) -> Result:
        self.calls.append(invocation)

        return self.result

    async def aclose(self) -> None:
        self.closed = True


@attrs.define(kw_only=True)
class _Gate(Invoker):
    url: URL
    opened: anyio.Event = attrs.field(factory=anyio.Event)
    entered: list[str] = attrs.field(factory=list)

    async def invoke(self, invocation: Invocation) -> Result:
        self.entered.append(invocation.method)
        if invocation.method.startswith("wait"):
            await self.opened.wait()

        return Result(value=invocation.method)

    async def aclose(self) -> None:
        pass


@pytest.fixture
def url() -> URL:
    return URL.parse("tri://127.0.0.1:50051/com.example.UserService").replace(
        attributes={APPLICATION_SCOPE: ApplicationScope()}
    )


@pytest.fixture
def ending(url):
    return lambda result: _Ending(result=result, url=url)


@pytest.fixture
def gate(url):
    return _Gate(url=url)


@pytest.fixture
def call():
    def create(method: str = "getUser", **attachments: str | bytes) -> Invocation:
        return Invocation(
            interface="com.example.UserService",
            method=method,
            definition=Method(name=method, request=(), response=None),
            attachments=attachments,
        )

    return create
