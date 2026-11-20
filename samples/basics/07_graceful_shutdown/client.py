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

# The consumer: it makes a call that takes 5 seconds. Stop the server while
# the call runs: the call still succeeds.

import asyncio

from dubbo import Dubbo
from dubbo.config import ConsumerConfig

from greeter import Greeter


async def main() -> None:
    # A call may take 10 seconds here, instead of 1 by default.
    app = Dubbo(consumer=ConsumerConfig(timeout=10))
    greeter = app.refer(Greeter, url="dubbo://127.0.0.1:20880")

    async with app:
        print("Calling; press Ctrl+C in the server window now")
        print(await greeter.greet("Watson"))


if __name__ == "__main__":
    asyncio.run(main())
