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

# The users and the inventory of the shop, served by one application.

import asyncio

import dubbo
from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig, ProtocolConfig, ProviderConfig

from shop import REGISTRIES, SERIALIZATION, Inventory, Item, User, Users

USERS = {1: User(id=1, name="Alice"), 2: User(id=2, name="Bob")}
ITEMS = {
    "book": Item(name="book", price=12.5, stock=10),
    "lamp": Item(name="lamp", price=30.0, stock=2),
    "piano": Item(name="piano", price=2000.0, stock=1),
}


def trace_id() -> str:
    # The gateway attaches a trace id to each request, and the orders service
    # passes it on with the calls it makes.
    return dubbo.incoming().attachments.get("trace-id", "-")


class UsersImpl(Users):
    async def get_user(self, user_id: int) -> User:
        print(f"[{trace_id()}] get_user({user_id})")
        if user_id not in USERS:
            raise RpcError(Status.NOT_FOUND, f"no user has ID {user_id}")
        return USERS[user_id]


class InventoryImpl(Inventory):
    async def get_item(self, name: str) -> Item:
        print(f"[{trace_id()}] get_item({name!r})")
        if name == "piano":
            # The stock of a piano is counted by hand.
            await asyncio.sleep(3)
        if name not in ITEMS:
            raise RpcError(Status.NOT_FOUND, f"the shop sells no {name}")
        return ITEMS[name]


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="shop-backend"),
        protocols={"tri": ProtocolConfig(port=50051)},
        registries=REGISTRIES,
        provider=ProviderConfig(serialization=SERIALIZATION),
    )
    app.export(UsersImpl())
    app.export(InventoryImpl())

    async with app:
        print("Serving users and inventory on port 50051; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
