#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import asyncio


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        print("Connection from", transport.get_extra_info("peername"))

    def data_received(self, data):
        message = data.decode()
        print("Data received:", message)
        self.transport.write(data)  # Echo the received data back

    def connection_lost(self, exc):
        print("Client disconnected")


async def run_server():
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: EchoServerProtocol(), "127.0.0.1", 8888)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(run_server())
