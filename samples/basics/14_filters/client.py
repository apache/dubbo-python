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

# The consumer: one application attaches the API key with a filter, and one
# does not.

import asyncio

from dubbo import Dubbo, RpcError
from dubbo.config import ConsumerConfig

import filters
from greeter import Greeter


async def greet(consumer: ConsumerConfig) -> str:
    app = Dubbo(consumer=consumer)
    greeter = app.refer(Greeter, url="dubbo://127.0.0.1:20880")
    async with app:
        try:
            return await greeter.greet("Alice")
        except RpcError as error:
            return f"{error.status.name}: {error.message}"


async def main() -> None:
    filters.register()
    print("With the key:", await greet(ConsumerConfig(filters=("api-key",), parameters={"api-key": "s3cret"})))
    print("Without:", await greet(ConsumerConfig()))


if __name__ == "__main__":
    asyncio.run(main())
