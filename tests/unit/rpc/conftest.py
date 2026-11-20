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

import abc
import typing

import attrs
import pytest

import dubbo
from dubbo import Invocation, Result


@dubbo.service("com.example.UserService")
class UserService(typing.Protocol):
    async def rename(self, id: int, name: str) -> str: ...
    @dubbo.method("findByName")
    async def find(self, name: str, limit: int = 10) -> list[str]: ...
    async def fail(self, error: str) -> None: ...
    async def sleep(self) -> None: ...

    def watch(self, query: str) -> dubbo.ServerStream[int]: ...
    def upload(self) -> dubbo.ClientStream[bytes, int]: ...
    def chat(self) -> dubbo.BidiStream[str, str]: ...


@dubbo.service("com.example.UserService")
class UserServiceServicer(abc.ABC):
    @abc.abstractmethod
    async def rename(self, id: int, name: str) -> str: ...
    @dubbo.method("findByName")
    @abc.abstractmethod
    async def find(self, name: str, limit: int = 10) -> list[str]: ...
    @abc.abstractmethod
    async def fail(self, error: str) -> None: ...
    @abc.abstractmethod
    async def sleep(self) -> None: ...

    @abc.abstractmethod
    async def watch(self, query: str, events: dubbo.SendStream[int]) -> None: ...
    @abc.abstractmethod
    async def upload(self, chunks: dubbo.ReceiveStream[bytes]) -> int: ...
    @abc.abstractmethod
    async def chat(self, stream: dubbo.Stream[str, str]) -> None: ...


@attrs.define(kw_only=True)
class _Recording:
    result: Result = attrs.field(factory=lambda: Result(value="answer"))
    calls: list[Invocation] = attrs.field(factory=list)

    async def invoke(self, invocation: Invocation) -> Result:
        self.calls.append(invocation)

        return self.result


@pytest.fixture
def contract():
    return UserService


@pytest.fixture
def servicer():
    return UserServiceServicer


@pytest.fixture
def recording():
    return _Recording()
