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

# A plain gRPC client, with no Dubbo in it, that calls dubbo_server.py.

import asyncio

import grpc

from greeter_pb2 import HelloRequest
from greeter_pb2_grpc import GreeterStub


async def main() -> None:
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = GreeterStub(channel)
        reply = await stub.SayHello(HelloRequest(name="gRPC"))
        print(reply.message)


if __name__ == "__main__":
    asyncio.run(main())
