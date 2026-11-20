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

# The Python provider: Greeter over Triple and UserService over Dubbo,
# registered in Nacos, where Java consumers find them.

import asyncio

import dubbo
from dubbo import Dubbo, RemoteError
from dubbo.config import ApplicationConfig, ProtocolConfig, RegistryConfig, ServiceConfig

from greeter_dubbo import GreeterServicer
from greeter_pb2 import HelloReply, HelloRequest
from users import User, UserService


def trace_id() -> str | bytes | None:
    # The attachments that the caller sent with the call being served.
    return dubbo.incoming().attachments.get("trace-id")


class GreeterImpl(GreeterServicer):
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        print(f"[{trace_id()}] say_hello({request.name})")
        return HelloReply(message=f"Hello, {request.name}, from Python!")

    async def say_hello_stream(self, request: HelloRequest, stream: dubbo.SendStream[HelloReply]) -> None:
        for count in range(1, 4):
            await stream.send(HelloReply(message=f"Hello #{count}, {request.name}, from Python!"))


class UserServiceImpl(UserService):
    async def get_user(self, id: int) -> User:
        print(f"[{trace_id()}] get_user({id})")
        if id != 1:
            # A Java exception, by its class name, as the Java server throws.
            raise RemoteError("java.lang.IllegalArgumentException", f"no user has ID {id}")
        return User(id=1, name="Alice", email="alice@example.com")


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="python-server"),
        registries={"default": RegistryConfig(address="nacos://127.0.0.1:8848")},
        protocols={"tri": ProtocolConfig(port=50051), "dubbo": ProtocolConfig(port=20880)},
    )
    # Each service on one protocol, as the Java side does: Protobuf messages
    # over Triple, Java objects over Dubbo.
    app.export(GreeterImpl(), config=ServiceConfig(protocols=("tri",)))
    app.export(UserServiceImpl(), config=ServiceConfig(protocols=("dubbo",)))

    async with app:
        print("Serving Greeter on port 50051 and UserService on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
