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

# The contracts of two services: an order service that calls an inventory
# service, so that context passes along a chain of calls.

import typing

import dubbo


@dubbo.service("org.apache.dubbo.samples.Orders")
class Orders(typing.Protocol):
    async def place_order(self, item: str, quantity: int) -> str: ...


@dubbo.service("org.apache.dubbo.samples.Inventory")
class Inventory(typing.Protocol):
    async def reserve(self, item: str, quantity: int) -> bool: ...
