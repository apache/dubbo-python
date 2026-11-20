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

# The provider: it implements the three streaming methods of greeter.proto.

import asyncio

import dubbo
from dubbo import Dubbo
from dubbo.config import ApplicationConfig

from greeter_dubbo import StreamGreeterServicer
from greeter_pb2 import HelloReply, HelloRequest


class StreamGreeterImpl(StreamGreeterServicer):
    # Server streaming: the handler gets a stream to send replies on. The
    # call ends when the handler returns.
    async def greet_many_times(self, request: HelloRequest, stream: dubbo.SendStream[HelloReply]) -> None:
        for count in range(1, 4):
            await stream.send(HelloReply(message=f"Hello #{count}, {request.name}!"))
            await asyncio.sleep(0.2)

    # Client streaming: the handler reads the requests with `async for` until
    # the caller ends them, then returns the one reply.
    async def greet_everyone(self, stream: dubbo.ReceiveStream[HelloRequest]) -> HelloReply:
        names = [request.name async for request in stream]
        return HelloReply(message=f"Hello, {', '.join(names)}!")

    # Bidirectional streaming: the handler sends and receives on one stream,
    # here a reply for each request as it arrives.
    async def chat(self, stream: dubbo.Stream[HelloReply, HelloRequest]) -> None:
        async for request in stream:
            await stream.send(HelloReply(message=f"Nice to meet you, {request.name}"))


async def main() -> None:
    app = Dubbo(application=ApplicationConfig(name="streaming-server"))
    app.export(StreamGreeterImpl())

    async with app:
        print("Serving on port 50051; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
