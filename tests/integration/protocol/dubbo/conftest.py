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
import dataclasses
import struct
import typing
from collections.abc import AsyncIterator
from typing import Any

import anyio
import hessian2
import pytest

import dubbo
from dubbo import RemoteError, RpcError, Status
from dubbo.protocol import Exporter
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.rpc.client import proxy
from dubbo.rpc.invocation import Invocation
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL


@hessian2.java_class("com.example.Address")
@dataclasses.dataclass
class Address:
    city: str


@hessian2.java_class("java.lang.IllegalStateException")
@dataclasses.dataclass
class IllegalState(Exception):
    detail_message: str = ""


@hessian2.java_class("com.example.User")
@dataclasses.dataclass
class User:
    name: str
    user_id: hessian2.Long
    address: Address


@dubbo.service("com.example.UserService")
class UserService(abc.ABC):
    @dubbo.method("find")
    @abc.abstractmethod
    async def find(self, name: str, user_id: hessian2.Long) -> User | None: ...

    @dubbo.method("forget")
    @abc.abstractmethod
    async def forget(self, name: str) -> None: ...

    @dubbo.method("fail")
    @abc.abstractmethod
    async def fail(self, how: str) -> str: ...

    @dubbo.method("sleep")
    @abc.abstractmethod
    async def sleep(self) -> str: ...


@dubbo.service("com.example.UserService")
class WiderUserService(typing.Protocol):
    @dubbo.method("find")
    async def find(self, name: str, user_id: hessian2.Long) -> User | None: ...

    @dubbo.method("missing")
    async def missing(self) -> str: ...


class UserServiceImpl(UserService):
    def __init__(self) -> None:
        self.started = anyio.Event()
        self.released = anyio.Event()
        self.cancelled = anyio.Event()
        self.forgotten: list[str] = []

    async def find(self, name: str, user_id: int) -> User | None:
        call = dubbo.incoming()
        call.response_attachments["served-by"] = "users"
        call.response_attachments["tag"] = call.attachments.get("tag", "")
        return None if name == "nobody" else User(name=name, user_id=user_id, address=Address(city="Hangzhou"))

    async def forget(self, name: str) -> None:
        self.forgotten.append(name)

    async def fail(self, how: str) -> str:
        if how == "rpc":
            raise RpcError(Status.NOT_FOUND, "no such user")
        if how == "declared":
            raise IllegalState("not now")
        if how == "remote":
            raise RemoteError("com.example.UserNotFound", "bob", fields={"code": 3})
        raise ValueError("broken")

    async def sleep(self) -> str:
        self.started.set()
        try:
            await self.released.wait()
            return ""
        finally:
            self.cancelled.set()


@pytest.fixture
async def protocol() -> AsyncIterator[DubboProtocol]:
    async with DubboProtocol() as protocol:
        yield protocol


@pytest.fixture
def impl() -> UserServiceImpl:
    return UserServiceImpl()


async def _export(protocol: DubboProtocol, impl: object, query: str = "") -> Exporter:
    url = URL.parse(f"dubbo://127.0.0.1:0/com.example.UserService{query}")
    return await protocol.export(url, dubbo.get_definition(UserService), ServiceInvoker.from_implementation(impl, url))


def _frame(flags: int, request_id: int, body: bytes, status: int = 0) -> bytes:
    return struct.pack(">HBBqI", 0xDABB, flags, status, request_id, len(body)) + body


def _find(arguments: tuple[Any, ...]) -> Invocation:
    find = next(method for method in dubbo.get_definition(UserService).methods if method.name == "find")
    return Invocation(interface="com.example.UserService", method="find", definition=find, arguments=arguments)


async def _refer(protocol: DubboProtocol, exporter: Exporter, query: str = "", contract: type = UserService) -> Any:
    url = URL.parse(f"dubbo://127.0.0.1:{exporter.url.port}/com.example.UserService{query}")
    return proxy(contract, (await protocol.refer(url, dubbo.get_definition(contract))).invoke)


@pytest.fixture
async def users(protocol: DubboProtocol, impl: UserServiceImpl) -> UserService:
    return await _refer(protocol, await _export(protocol, impl))


@pytest.fixture
def export():
    return _export


@pytest.fixture
def refer():
    return _refer


@pytest.fixture
def frame():
    return _frame


@pytest.fixture
def find_invocation():
    return _find


@pytest.fixture
def user_service():
    return UserService


@pytest.fixture
def wider_service():
    return WiderUserService


@pytest.fixture
def implementation_type():
    return UserServiceImpl


@pytest.fixture
def user_type():
    return User


@pytest.fixture
def address_type():
    return Address
