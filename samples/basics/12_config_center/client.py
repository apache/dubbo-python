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

# The consumer: it calls the Greeter once a second until three calls have
# succeeded. Its calls time out until a rule in the configuration center gives
# them longer.

import asyncio

from dubbo import Dubbo, RpcError
from dubbo.config import ApplicationConfig, ConfigCenterConfig

from greeter import Greeter


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="config-center-client"),
        config_center=ConfigCenterConfig(address="zookeeper://127.0.0.1:2181"),
    )
    greeter = app.refer(Greeter)

    async with app:
        succeeded = 0
        while succeeded < 3:
            try:
                print(await greeter.greet("Alice"))
                succeeded += 1
            except RpcError as error:
                print(f"{error.status.name}: {error.message}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
