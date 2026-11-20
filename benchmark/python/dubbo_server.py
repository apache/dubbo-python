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

"""Dubbo Python serving the benchmark service over one protocol, on one event loop in one process."""

import argparse

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from contract import BenchImpl, BenchServiceImpl, run


async def serve(protocol: str, port: int) -> None:
    app = Dubbo(
        application=ApplicationConfig(name="bench-server"),
        protocols={protocol: ProtocolConfig(name=protocol, host="127.0.0.1", port=port)},
        env_prefix=None,
    )
    app.export(BenchImpl() if protocol == "tri" else BenchServiceImpl())
    async with app:
        await app.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=["tri", "dubbo"], default="tri")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--loop", choices=["asyncio", "uvloop"], default="asyncio")
    args = parser.parse_args()
    run(serve(args.protocol, args.port), args.loop)


if __name__ == "__main__":
    main()
