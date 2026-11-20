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

# The contracts of the services of the shop, and the settings they share.
# Every process imports this module, so they agree on the types and the
# registry.

import dataclasses
import typing

import dubbo
import hessian2
from dubbo.config import RegistryConfig

# Each application registers its services in ZooKeeper, and finds those it
# calls there.
REGISTRIES = {"zookeeper": RegistryConfig(address="zookeeper://127.0.0.1:2181")}
# Over Triple, Hessian 2 carries Python types and several parameters, where
# protobuf carries one message. Providers name it, and their consumers take
# it from the registry.
SERIALIZATION = "hessian2"


# Hessian 2 carries an object under a Java class name, field by field, so
# that Java and Go read it too; the name is any that the services agree on.
@hessian2.java_class("org.apache.dubbo.samples.shop.User")
@dataclasses.dataclass
class User:
    id: int
    name: str


@hessian2.java_class("org.apache.dubbo.samples.shop.Item")
@dataclasses.dataclass
class Item:
    name: str
    price: float
    stock: int


@hessian2.java_class("org.apache.dubbo.samples.shop.Order")
@dataclasses.dataclass
class Order:
    id: int
    user: str
    item: str
    quantity: int
    total: float


@dubbo.service("org.apache.dubbo.samples.shop.Users")
class Users(typing.Protocol):
    async def get_user(self, user_id: int) -> User: ...


@dubbo.service("org.apache.dubbo.samples.shop.Inventory")
class Inventory(typing.Protocol):
    async def get_item(self, name: str) -> Item: ...


@dubbo.service("org.apache.dubbo.samples.shop.Orders")
class Orders(typing.Protocol):
    async def place_order(self, user_id: int, item: str, quantity: int) -> Order: ...
