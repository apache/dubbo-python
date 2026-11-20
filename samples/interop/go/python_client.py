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

# The Python consumer: it finds the Go service in Nacos and calls it.

import asyncio

import dubbo
from dubbo import Dubbo, RpcError
from dubbo.config import ApplicationConfig, RegistryConfig

from greeter_dubbo import Greeter
from greeter_pb2 import HelloRequest


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="python-client"),
        registries={"default": RegistryConfig(address="nacos://127.0.0.1:8848")},
    )
    # No URL: the providers come from the registry, in whatever language.
    greeter = app.refer(Greeter)

    async with app:
        # Every call in the block attaches the trace id.
        with dubbo.outgoing({"trace-id": "py-4bf9"}):
            reply = await greeter.say_hello(HelloRequest(name="Alice"))
            print(reply.message)
            async with greeter.say_hello_stream(HelloRequest(name="Bob")) as replies:
                async for reply in replies:
                    print(reply.message)

            # A failure arrives as an RpcError with the status of the provider.
            try:
                await greeter.say_hello(HelloRequest())
            except RpcError as error:
                print(error)


if __name__ == "__main__":
    asyncio.run(main())
