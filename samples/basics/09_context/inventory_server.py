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

# The inventory provider, at the end of the chain.

import asyncio

import dubbo
from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from services import Inventory


class InventoryImpl(Inventory):
    async def reserve(self, item: str, quantity: int) -> bool:
        # The attachments arrived from the order service, which did not set
        # them: it passed on those it received from the client.
        attachments = dubbo.incoming().attachments
        print(f"[trace {attachments['trace-id']}] Reserving {quantity} x {item} for {attachments['user']}")
        return True


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="inventory-server"),
        protocols={"dubbo": ProtocolConfig(port=20881)},
    )
    app.export(InventoryImpl())

    async with app:
        print("Serving on port 20881; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
