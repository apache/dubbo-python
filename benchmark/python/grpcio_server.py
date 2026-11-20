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

"""grpcio, the gRPC library of Google, serving the Bench service of bench.proto with grpc.aio, for comparison."""

import argparse

import grpc

from bench_pb2 import Payload
from contract import run


async def echo(request: Payload, context: grpc.aio.ServicerContext) -> Payload:
    return request


async def serve(port: int) -> None:
    server = grpc.aio.server()
    method = grpc.unary_unary_rpc_method_handler(
        echo, request_deserializer=Payload.FromString, response_serializer=Payload.SerializeToString
    )
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("org.apache.dubbo.benchmark.Bench", {"Echo": method}),)
    )
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--loop", choices=["asyncio", "uvloop"], default="asyncio")
    args = parser.parse_args()
    run(serve(args.port), args.loop)


if __name__ == "__main__":
    main()
