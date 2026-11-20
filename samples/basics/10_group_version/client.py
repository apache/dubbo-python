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

# The consumer: it calls the version of the Greeter named on its command
# line, 1.0.0 by default:
#
#   python client.py
#   python client.py 2.0.0

import asyncio
import sys

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ConsumerConfig, RegistryConfig

from greeter import Greeter


async def main(version: str) -> None:
    # ConsumerConfig(version=...) applies to every reference of the
    # application; app.refer(Greeter, config=ReferenceConfig(version=...))
    # would choose it for one service only.
    app = Dubbo(
        application=ApplicationConfig(name="group-version-client"),
        registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
        consumer=ConsumerConfig(version=version),
    )
    greeter = app.refer(Greeter)

    async with app:
        print(f"Version {version}:", await greeter.greet("Alice"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "1.0.0"))
