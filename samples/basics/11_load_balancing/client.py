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

# The consumer: it calls the workers with different load balances and
# clusters, and counts where the calls went.

import asyncio
from collections import Counter

from dubbo import Dubbo, RpcError
from dubbo.config import ReferenceConfig

from worker import Worker

FAST, SLOW, OVERLOADED = "dubbo://127.0.0.1:20880", "dubbo://127.0.0.1:20881", "dubbo://127.0.0.1:20882"


async def call(urls: tuple[str, ...], calls: int, concurrency: int = 1, **settings: str) -> Counter[str]:
    """Make `calls` calls, `concurrency` at a time, and count who answered them, or how they failed."""
    # The reference calls the providers its urls name. An application refers
    # to a service once, so each setting gets an application of its own here.
    app = Dubbo()
    worker = app.refer(Worker, config=ReferenceConfig(urls=urls, **settings))
    results: Counter[str] = Counter()

    async def caller(count: int) -> None:
        for _ in range(count):
            try:
                results[await worker.work("task")] += 1
            except RpcError as error:
                results[error.status.name] += 1

    async with app, asyncio.TaskGroup() as group:
        for _ in range(concurrency):
            group.create_task(caller(calls // concurrency))
    return results


def show(title: str, results: Counter[str]) -> None:
    print(f"{title}: {', '.join(f'{name} {count}' for name, count in sorted(results.items()))}")


async def main() -> None:
    # Load balancing chooses the provider of each call.
    show("roundrobin", await call((FAST, SLOW), 6, loadbalance="roundrobin"))
    show("leastactive", await call((FAST, SLOW), 40, concurrency=8, loadbalance="leastactive"))

    # The cluster decides what a failed attempt leads to.
    show("failover", await call((FAST, OVERLOADED), 6, loadbalance="roundrobin"))
    show("failfast", await call((FAST, OVERLOADED), 6, loadbalance="roundrobin", cluster="failfast"))


if __name__ == "__main__":
    asyncio.run(main())
