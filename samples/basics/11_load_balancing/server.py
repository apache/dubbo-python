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

# Three providers of the Worker, each with its own trait. They run in one
# process to keep the sample short; in production each is a process of its
# own, usually on a machine of its own.
#
#   fast        on port 20880: answers at once
#   slow        on port 20881: takes 0.2 seconds
#   overloaded  on port 20882: rejects every call as UNAVAILABLE

import asyncio
from contextlib import AsyncExitStack

from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig, ProtocolConfig

from worker import Worker


class FastWorker(Worker):
    async def work(self, task: str) -> str:
        return "fast"


class SlowWorker(Worker):
    async def work(self, task: str) -> str:
        await asyncio.sleep(0.2)
        return "slow"


class OverloadedWorker(Worker):
    async def work(self, task: str) -> str:
        raise RpcError(Status.UNAVAILABLE, "overloaded")


async def main() -> None:
    workers = {20880: FastWorker(), 20881: SlowWorker(), 20882: OverloadedWorker()}
    async with AsyncExitStack() as stack:
        for port, worker in workers.items():
            app = Dubbo(
                application=ApplicationConfig(name=f"worker-{port}"),
                protocols={"dubbo": ProtocolConfig(port=port)},
            )
            app.export(worker)
            await stack.enter_async_context(app)

        print("Serving on ports 20880, 20881 and 20882; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
