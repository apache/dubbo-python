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

# The consumer: it makes one call of each streaming style.

import asyncio

from dubbo import Dubbo

from greeter_dubbo import StreamGreeter
from greeter_pb2 import HelloRequest


async def main() -> None:
    app = Dubbo()
    greeter = app.refer(StreamGreeter, url="tri://127.0.0.1:50051")

    async with app:
        # Server streaming: a streaming call is a context manager; leaving
        # the block ends the call. `async for` reads the replies as they come.
        print("Server streaming:")
        async with greeter.greet_many_times(HelloRequest(name="Alice")) as replies:
            async for reply in replies:
                print(" ", reply.message)

        # Client streaming: send the requests, end them, then receive the reply.
        print("Client streaming:")
        async with greeter.greet_everyone() as stream:
            for name in ["Alice", "Bob", "Carol"]:
                await stream.send(HelloRequest(name=name))
            await stream.end()
            reply = await stream.receive()
            print(" ", reply.message)

        # Bidirectional streaming: here each request waits for its reply, but
        # both sides may also send and receive independently, for example in
        # two tasks.
        print("Bidirectional streaming:")
        async with greeter.chat() as stream:
            for name in ["Alice", "Bob"]:
                await stream.send(HelloRequest(name=name))
                reply = await stream.receive()
                print(" ", reply.message)
            await stream.end()


if __name__ == "__main__":
    asyncio.run(main())
