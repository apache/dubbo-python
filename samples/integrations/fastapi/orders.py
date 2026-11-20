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

# The orders service: it calls the users and the inventory services for each
# order.

import asyncio
import itertools

import dubbo
from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig, ConsumerConfig, ProtocolConfig, ProviderConfig

from shop import REGISTRIES, SERIALIZATION, Inventory, Order, Orders, Users


class OrdersImpl(Orders):
    def __init__(self, users: Users, inventory: Inventory) -> None:
        self.users = users
        self.inventory = inventory
        self.ids = itertools.count(1)

    async def place_order(self, user_id: int, item: str, quantity: int) -> Order:
        trace_id = dubbo.incoming().attachments.get("trace-id", "-")
        print(f"[{trace_id}] place_order({user_id}, {item!r}, {quantity})")
        if quantity < 1:
            raise RpcError(Status.INVALID_ARGUMENT, "an order is of one item or more")

        # The two calls run at once. The first to fail fails the order: its
        # RpcError, raised here, reaches the caller with its status.
        user, stock = await asyncio.gather(self.users.get_user(user_id), self.inventory.get_item(item))
        if stock.stock < quantity:
            raise RpcError(Status.FAILED_PRECONDITION, f"only {stock.stock} {item} left")
        return Order(id=next(self.ids), user=user.name, item=item, quantity=quantity, total=stock.price * quantity)


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="shop-orders"),
        protocols={"tri": ProtocolConfig(port=50052)},
        registries=REGISTRIES,
        provider=ProviderConfig(serialization=SERIALIZATION),
        # Each call to the users and the inventory may take 1 second.
        consumer=ConsumerConfig(timeout=1),
    )
    users = app.refer(Users)
    inventory = app.refer(Inventory)
    app.export(OrdersImpl(users, inventory))

    async with app:
        print("Serving orders on port 50052; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
