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

# The provider: its code names the configuration center and nothing more of
# its environment; the registry comes from the center.

import asyncio
import logging

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ConfigCenterConfig

from greeter import Greeter


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        # Takes longer than the 1 second a call may take by default.
        await asyncio.sleep(1.5)
        return f"Hello, {name}!"


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("dubbo.accesslog").setLevel(logging.INFO)

    app = Dubbo(
        application=ApplicationConfig(name="config-center-server"),
        config_center=ConfigCenterConfig(address="zookeeper://127.0.0.1:2181"),
    )
    app.export(GreeterImpl())

    async with app:
        print(f"Serving; registered with {', '.join(app.config.registries)} from the configuration center")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
