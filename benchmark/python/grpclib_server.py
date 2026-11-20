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

"""grpclib, the gRPC library in pure Python, serving the Bench service of bench.proto, for comparison."""

import argparse

from grpclib.const import Cardinality, Handler
from grpclib.server import Server, Stream

from bench_pb2 import Payload
from contract import run


class Bench:
    async def echo(self, stream: Stream[Payload, Payload]) -> None:
        request = await stream.recv_message()
        await stream.send_message(request)

    def __mapping__(self) -> dict[str, Handler]:
        return {"/org.apache.dubbo.benchmark.Bench/Echo": Handler(self.echo, Cardinality.UNARY_UNARY, Payload, Payload)}


async def serve(port: int) -> None:
    server = Server([Bench()])
    await server.start("127.0.0.1", port)
    await server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--loop", choices=["asyncio", "uvloop"], default="asyncio")
    args = parser.parse_args()
    run(serve(args.port), args.loop)


if __name__ == "__main__":
    main()
