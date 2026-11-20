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

# The consumer: it attaches a trace id to each call.

import asyncio

import dubbo
from dubbo import Dubbo

from greeter import Greeter


async def main() -> None:
    app = Dubbo()
    greeter = app.refer(Greeter, url="dubbo://127.0.0.1:20880")

    async with app:
        for trace_id, name in [("4bf92f35", "Alice"), ("a3ce929d", "Bob")]:
            with dubbo.outgoing({"trace-id": trace_id}):
                print(await greeter.greet(name))


if __name__ == "__main__":
    asyncio.run(main())
