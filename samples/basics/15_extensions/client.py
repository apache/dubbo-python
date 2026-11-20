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

# The consumer: it calls the Greeter that server.py serves.

import asyncio

from dubbo import Dubbo

from greeter import Greeter


async def main() -> None:
    # A consumer that calls providers by their addresses needs no configuration.
    app = Dubbo()

    # refer() returns an object that implements the contract by calling the
    # provider. The URL names the protocol and address of the provider; the
    # registry sample shows how to find providers without knowing them.
    greeter = app.refer(Greeter, url="dubbo://127.0.0.1:20880")

    # Calls work while the application runs, that is inside `async with`.
    async with app:
        for name in ["Alice", "Bob"]:
            reply = await greeter.greet(name)
            print(reply)


if __name__ == "__main__":
    asyncio.run(main())
