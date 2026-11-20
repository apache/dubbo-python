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

# A plain gRPC server, with no Dubbo in it, that dubbo_client.py calls.

import asyncio
import contextlib

import grpc

from greeter_pb2 import HelloReply, HelloRequest
from greeter_pb2_grpc import GreeterServicer, add_GreeterServicer_to_server


class GreeterImpl(GreeterServicer):
    async def SayHello(self, request: HelloRequest, context: grpc.aio.ServicerContext) -> HelloReply:
        return HelloReply(message=f"Hello, {request.name}, from gRPC!")


async def main() -> None:
    server = grpc.aio.server()
    add_GreeterServicer_to_server(GreeterImpl(), server)
    server.add_insecure_port("127.0.0.1:50052")
    await server.start()
    print("Serving on port 50052; press Ctrl+C to stop")
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)


if __name__ == "__main__":
    # asyncio.run() raises KeyboardInterrupt once Ctrl+C has stopped the server.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
