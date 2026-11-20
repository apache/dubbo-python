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

# The consumer: it shows where calls go, with and without a tag. Run it before
# and after publishing each rule.

import asyncio

import dubbo
from dubbo import Dubbo
from dubbo.config import ApplicationConfig, RegistryConfig

from greeter import Greeter


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="routing-client"),
        registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
    )
    greeter = app.refer(Greeter)

    async def where(name: str) -> str:
        # The instances that answered 20 calls for name.
        instances = {(await greeter.greet(name)).split(" ")[0] for _ in range(20)}
        return ", ".join(sorted(instances))

    async with app:
        # A call that asks for no tag goes to the untagged instances only.
        print(f"Bob: {await where('Bob')}")
        print(f"Alice: {await where('Alice')}")

        # A call that asks for a tag goes to the instances of that tag, such
        # as test traffic to a new release, else to the untagged instances.
        for tag in ["gray", "canary"]:
            with dubbo.outgoing({"dubbo.tag": tag}):
                print(f"Bob, tagged {tag}: {await where('Bob')}")


if __name__ == "__main__":
    asyncio.run(main())
