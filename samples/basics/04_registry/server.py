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

# The provider: it registers the Greeter with a registry, so that consumers
# find it by its service name. Run several to see calls spread across them.

import asyncio
import os

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, RegistryConfig

from greeter import Greeter


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        # The process ID tells the replies of different servers apart.
        return f"Hello, {name}! (from server {os.getpid()})"


async def main() -> None:
    # The registry is one more part of the configuration. On start, the
    # application registers its services there; on stop, it removes them.
    # A registry needs the application name, which groups its instances.
    app = Dubbo(
        application=ApplicationConfig(name="registry-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
        registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
    )
    app.export(GreeterImpl())

    async with app:
        print("Serving and registered; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
