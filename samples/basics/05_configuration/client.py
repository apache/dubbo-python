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

# The consumer: client.yaml says how to find the Greeter and how to call it,
# so the code only refers to the contract.

import asyncio
from pathlib import Path

from dubbo import Dubbo

from greeter import Greeter

HERE = Path(__file__).parent


async def main() -> None:
    app = Dubbo(HERE / "client.yaml")
    greeter = app.refer(Greeter)

    async with app:
        print(await greeter.greet("Alice"))
        # The provider allows this method 5 seconds, and the consumer takes
        # that from the registry, so the 2 seconds it takes are fine.
        print(await greeter.greet_slowly("Bob"))


if __name__ == "__main__":
    asyncio.run(main())
