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

# The contracts of the supply services, which the services and the planner
# both import. The docstrings are what the agent reads to choose its tools.

import dataclasses
import typing

import dubbo
import hessian2

# The services serve over the Dubbo protocol, which carries these types with
# Hessian 2, as most Java services do.
ADDRESS = "dubbo://127.0.0.1:20880"


@hessian2.java_class("org.apache.dubbo.samples.supply.Stock")
@dataclasses.dataclass
class Stock:
    sku: str
    name: str
    on_hand: int
    in_transit: int


@hessian2.java_class("org.apache.dubbo.samples.supply.Quote")
@dataclasses.dataclass
class Quote:
    supplier: str
    sku: str
    unit_price: float
    lead_days: int
    min_order: int


@hessian2.java_class("org.apache.dubbo.samples.supply.Draft")
@dataclasses.dataclass
class Draft:
    id: str
    supplier: str
    sku: str
    quantity: int
    total: float


@dubbo.service("org.apache.dubbo.samples.supply.Inventory")
class Inventory(typing.Protocol):
    async def low_stock(self, warehouse: str) -> list[Stock]:
        """Return the SKUs of a warehouse whose stock is running low.

        Args:
            warehouse: Code of the warehouse, such as EAST.
        """
        ...


@dubbo.service("org.apache.dubbo.samples.supply.Forecast")
class Forecast(typing.Protocol):
    async def predict(self, sku: str, days: int) -> int:
        """Return how many units of a SKU will sell in the coming days, the sale included.

        Args:
            sku: The SKU.
            days: Number of days from today.
        """
        ...


@dubbo.service("org.apache.dubbo.samples.supply.Suppliers")
class Suppliers(typing.Protocol):
    async def quotes(self, sku: str) -> list[Quote]:
        """Return what each supplier of a SKU asks for it, how many days its goods take to arrive, and its minimum order.

        Args:
            sku: The SKU.
        """
        ...


@dubbo.service("org.apache.dubbo.samples.supply.Purchasing")
class Purchasing(typing.Protocol):
    async def draft(self, supplier: str, sku: str, quantity: int) -> Draft:
        """Draft a purchase order, for a buyer to send.

        Args:
            supplier: The supplier.
            sku: The SKU.
            quantity: Number of units.
        """
        ...
