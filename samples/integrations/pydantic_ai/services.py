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

# The supply services of a company, in one application: in a real company,
# each is a service of its own, often in Java.

import asyncio
import itertools

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from supply import Draft, Forecast, Inventory, Purchasing, Quote, Stock, Suppliers

STOCK = {
    "EAST": [
        Stock(sku="TEA-OOLONG-250G", name="Oolong tea, 250 g", on_hand=120, in_transit=0),
        Stock(sku="MUG-CERAMIC-WHITE", name="White ceramic mug", on_hand=40, in_transit=200),
        Stock(sku="FLASK-500ML", name="Vacuum flask, 500 ml", on_hand=15, in_transit=0),
    ]
}
# Units a day before the sale, and how many times more during it.
DAILY = {"TEA-OOLONG-250G": (20, 5), "MUG-CERAMIC-WHITE": (8, 3), "FLASK-500ML": (12, 6)}
SALE_STARTS, SALE_DAYS = 7, 3
QUOTES = {
    "TEA-OOLONG-250G": [
        Quote(supplier="Hangzhou Leaf", sku="TEA-OOLONG-250G", unit_price=18.0, lead_days=10, min_order=100),
        Quote(supplier="Fujian Hills", sku="TEA-OOLONG-250G", unit_price=21.5, lead_days=4, min_order=50),
    ],
    "MUG-CERAMIC-WHITE": [
        Quote(supplier="Jingdezhen Kiln", sku="MUG-CERAMIC-WHITE", unit_price=9.0, lead_days=5, min_order=200),
    ],
    "FLASK-500ML": [
        Quote(supplier="Yongkang Steel", sku="FLASK-500ML", unit_price=45.0, lead_days=6, min_order=100),
        Quote(supplier="Ningbo Home", sku="FLASK-500ML", unit_price=52.0, lead_days=3, min_order=20),
    ],
}
PRICES = {(quote.supplier, quote.sku): quote.unit_price for quotes in QUOTES.values() for quote in quotes}


class InventoryImpl(Inventory):
    async def low_stock(self, warehouse: str) -> list[Stock]:
        print(f"low_stock({warehouse!r})")
        return STOCK.get(warehouse, [])


class ForecastImpl(Forecast):
    async def predict(self, sku: str, days: int) -> int:
        print(f"predict({sku!r}, {days})")
        daily, uplift = DAILY.get(sku, (0, 1))
        sale = max(0, min(days, SALE_STARTS + SALE_DAYS) - SALE_STARTS)
        return daily * (days - sale) + daily * uplift * sale


class SuppliersImpl(Suppliers):
    async def quotes(self, sku: str) -> list[Quote]:
        print(f"quotes({sku!r})")
        return QUOTES.get(sku, [])


class PurchasingImpl(Purchasing):
    def __init__(self) -> None:
        self._ids = itertools.count(1)

    async def draft(self, supplier: str, sku: str, quantity: int) -> Draft:
        print(f"draft({supplier!r}, {sku!r}, {quantity})")
        total = PRICES.get((supplier, sku), 0.0) * quantity
        return Draft(id=f"PO-{next(self._ids):04d}", supplier=supplier, sku=sku, quantity=quantity, total=total)


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="supply-services"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
    )
    for service in (InventoryImpl(), ForecastImpl(), SuppliersImpl(), PurchasingImpl()):
        app.export(service)

    async with app:
        print("Serving inventory, forecast, suppliers and purchasing on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
