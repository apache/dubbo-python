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

# The order provider: it serves the client and calls the inventory service.

import asyncio

import dubbo
from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from services import Inventory, Orders


class OrdersImpl(Orders):
    def __init__(self, inventory: Inventory) -> None:
        self.inventory = inventory

    async def place_order(self, item: str, quantity: int) -> str:
        # dubbo.incoming() is the call this handler serves: the attachments
        # the caller sent, where it calls from, and the attachments to send
        # back.
        call = dubbo.incoming()
        print(f"[trace {call.attachments['trace-id']}] Order from {call.attachments['user']} at {call.peer}")

        # Calls made while serving a call send on the attachments it received,
        # so the trace ID and the user reach the inventory service unasked.
        if not await self.inventory.reserve(item, quantity):
            return "Out of stock"

        call.response_attachments["served-by"] = "order-server"
        return f"Ordered {quantity} x {item}"


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="order-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
    )
    inventory = app.refer(Inventory, url="dubbo://127.0.0.1:20881")
    app.export(OrdersImpl(inventory))

    async with app:
        print("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
