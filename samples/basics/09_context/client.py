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

# The consumer: it attaches a trace ID and a user to its call, and reads what
# the order service attached to its reply.

import asyncio

import dubbo
from dubbo import Dubbo

from services import Orders


async def main() -> None:
    app = Dubbo()
    orders = app.refer(Orders, url="dubbo://127.0.0.1:20880")

    async with app:
        # Every call in the block sends these attachments: key-value pairs
        # that travel beside the arguments, as headers do in HTTP.
        with dubbo.outgoing({"trace-id": "4bf92f35", "user": "alice"}) as call:
            print(await orders.place_order("book", 2))

        # The last call of the block leaves the attachments of its reply.
        print(f"Served by {call.response_attachments['served-by']}")


if __name__ == "__main__":
    asyncio.run(main())
