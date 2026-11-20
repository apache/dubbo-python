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

# Version 2.0.0 of the Greeter, which greets differently. It runs beside
# version 1.0.0, and only consumers that ask for it call it.

import asyncio

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, ProviderConfig, RegistryConfig

from greeter import Greeter

VERSION = "2.0.0"
PORT = 20881


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        return f"Good to see you, {name}!"


async def main() -> None:
    # The version, like the group, is part of the identity of the services
    # the provider registers: consumers find a provider by name, group and
    # version together.
    app = Dubbo(
        application=ApplicationConfig(name=f"greeter-v{VERSION}"),
        protocols={"dubbo": ProtocolConfig(port=PORT)},
        registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
        provider=ProviderConfig(version=VERSION),
    )
    app.export(GreeterImpl())

    async with app:
        print(f"Serving version {VERSION} on port {PORT}; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
