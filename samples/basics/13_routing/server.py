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

# Three instances of one provider application, registered with ZooKeeper:
#
#   stable-1  on port 20880
#   stable-2  on port 20881
#   gray      on port 20882, tagged "gray" by its configuration: a new
#             release that only test traffic should reach for now
#
# They run in one process to keep the sample short; in production each is a
# process of its own.

import asyncio
from contextlib import AsyncExitStack

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, ProviderConfig, RegistryConfig

from greeter import Greeter

INSTANCES = {"stable-1": (20880, None), "stable-2": (20881, None), "gray": (20882, "gray")}


class GreeterImpl(Greeter):
    def __init__(self, instance: str) -> None:
        self.instance = instance

    async def greet(self, name: str) -> str:
        return f"{self.instance} greets {name}"


async def main() -> None:
    async with AsyncExitStack() as stack:
        for instance, (port, tag) in INSTANCES.items():
            app = Dubbo(
                application=ApplicationConfig(name="routing-server"),
                protocols={"dubbo": ProtocolConfig(port=port)},
                registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
                # The tag is published with the address of the instance. A
                # deployment usually sets it outside the code, as with
                # DUBBO__PROVIDER__TAG=gray.
                provider=ProviderConfig(tag=tag),
            )
            app.export(GreeterImpl(instance))
            await stack.enter_async_context(app)

        print("Serving stable-1, stable-2 and gray; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
