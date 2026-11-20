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

# The consumer: it finds the providers of the Greeter in the registry and
# spreads its calls across them.

import asyncio

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, RegistryConfig

from greeter import Greeter


async def main() -> None:
    # The same registry as the server, and no address of any provider.
    app = Dubbo(
        application=ApplicationConfig(name="registry-client"),
        registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
    )

    # Without a URL, refer() discovers the providers of the Greeter through
    # the registry, and follows them as they come and go.
    greeter = app.refer(Greeter)

    # Starting waits up to 3 seconds for a provider, and fails if none is
    # found; each call then goes to one of them, chosen at random by default.
    async with app:
        for name in ["Alice", "Bob", "Carol", "Dave"]:
            print(await greeter.greet(name))


if __name__ == "__main__":
    asyncio.run(main())
