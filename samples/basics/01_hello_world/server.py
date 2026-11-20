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

# The provider: it implements the Greeter contract and serves it until Ctrl+C.

import asyncio

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from greeter import Greeter


# The implementation subclasses the contract, so a type checker sees a
# method that is missing or has the wrong signature.
class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        print(f"Greeting {name}")
        return f"Hello, {name}!"


async def main() -> None:
    # The application has a name, and here one protocol: the Dubbo protocol on
    # port 20880, which carries Python values such as str, int, list and dict
    # in the Hessian 2 format that Java reads.
    app = Dubbo(
        application=ApplicationConfig(name="hello-world-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
    )
    app.export(GreeterImpl())

    # The application starts when `async with` enters, and stops when it
    # leaves. serve_forever() returns on Ctrl+C or SIGTERM, which then stops
    # the application gracefully: running calls finish first.
    async with app:
        print("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
