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

# The provider: it implements the Greeter of greeter.proto and serves it over
# the Triple protocol until Ctrl+C.

import asyncio

from dubbo import Dubbo
from dubbo.config import ApplicationConfig

from greeter_dubbo import GreeterServicer
from greeter_pb2 import HelloReply, HelloRequest


# The generated GreeterServicer is an abstract class with one method per rpc
# of the proto file, named in Python style: SayHello becomes say_hello.
class GreeterImpl(GreeterServicer):
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        print(f"Greeting {request.name}")
        return HelloReply(message=f"Hello, {request.name}!")


async def main() -> None:
    # With no protocol configured, an application serves Triple on port 50051.
    # Triple runs over HTTP/2 and carries Protobuf messages as gRPC does.
    app = Dubbo(application=ApplicationConfig(name="protobuf-server"))
    app.export(GreeterImpl())

    async with app:
        print("Serving on port 50051; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
