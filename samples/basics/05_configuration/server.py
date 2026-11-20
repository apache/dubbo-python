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

# The provider: it reads its configuration from server.yaml, which the
# environment can override.

import asyncio
import logging
from pathlib import Path

from dubbo import Dubbo

from greeter import Greeter

HERE = Path(__file__).parent


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"

    async def greet_slowly(self, name: str) -> str:
        await asyncio.sleep(2)
        return f"Hello... {name}!"


async def main() -> None:
    # The framework logs through the standard logging module and leaves its
    # setup to the application; INFO shows the calls that accesslog logs.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # A file as a source is read by the parser its suffix selects.
    # Environment variables starting with DUBBO__ override it.
    app = Dubbo(HERE / "server.yaml")
    app.export(GreeterImpl())

    async with app:
        # The configuration is read when the application starts; app.config
        # then holds the result of all its layers.
        config = app.config
        print(f"{config.application.name} serving on port {config.protocols['dubbo'].port}")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
