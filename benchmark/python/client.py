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

"""A closed-loop load of Python consumers: each of ``--concurrency`` tasks calls again as soon as its call returns.

The tasks are spread over ``--processes`` processes, each with one event
loop, which start together once all have connected; it prints ``started``
then. Calls during ``--warmup`` are not counted. It prints the result as
JSON: the calls and errors counted, the calls per second, the CPU seconds
the consumers spent meanwhile, and the latency percentiles in microseconds
with the histogram they come from.
"""

import argparse
import asyncio
import collections
import json
import math
import os
import time
from multiprocessing import get_context
from multiprocessing.synchronize import Barrier
from queue import Queue

from dubbo import Dubbo, RpcError
from dubbo.config import ApplicationConfig

from bench_pb2 import Payload
from contract import Bench, BenchService, run

# Latencies are counted in buckets about 1% wide: bucket b holds those of e ** (b / 100) to e ** ((b + 1) / 100) ns.
_BUCKETS_PER_E = 100
PERCENTILES = (50, 90, 99, 99.9)


def bucket(nanoseconds: int) -> int:
    return int(math.log(max(nanoseconds, 1)) * _BUCKETS_PER_E)


def percentiles(histogram: dict[int, int]) -> dict[str, float]:
    """Return the latency percentiles, and the largest, in microseconds, each the middle of its bucket."""
    total = sum(histogram.values())
    result, seen = {}, 0
    wanted = list(PERCENTILES)
    for each in sorted(histogram):
        seen += histogram[each]
        while wanted and seen >= total * wanted[0] / 100:
            result[f"p{wanted.pop(0):g}"] = _microseconds(each)
    if histogram:
        result["max"] = _microseconds(max(histogram))
    return result


def _microseconds(bucket: int) -> float:
    return round(math.exp((bucket + 0.5) / _BUCKETS_PER_E) / 1000, 1)


async def load(
    args: argparse.Namespace, concurrency: int, start: Barrier
) -> tuple[dict[int, int], dict[str, int], float]:
    app = Dubbo(application=ApplicationConfig(name="bench-client"), env_prefix=None)
    payload = os.urandom(args.size)
    if args.protocol == "tri":
        bench = app.refer(Bench, url=args.url)
        request = Payload(data=payload)

        def call():
            return bench.echo(request)
    else:
        service = app.refer(BenchService, url=args.url)

        def call():
            return service.echo(payload)

    histogram: collections.Counter[int] = collections.Counter()
    errors: collections.Counter[str] = collections.Counter()
    async with app:
        await call()  # Connects before the start.
        await asyncio.to_thread(start.wait)
        began = time.perf_counter()
        counted, end = began + args.warmup, began + args.warmup + args.duration

        async def worker() -> None:
            while (now := time.perf_counter()) < end:
                sent = time.perf_counter_ns()
                try:
                    await call()
                except RpcError as error:
                    if now >= counted:
                        errors[error.status.name] += 1
                    continue
                if now >= counted:
                    histogram[bucket(time.perf_counter_ns() - sent)] += 1

        async def measure_cpu() -> float:
            await asyncio.sleep(counted - time.perf_counter())
            cpu = time.process_time()
            await asyncio.sleep(end - time.perf_counter())
            return time.process_time() - cpu

        async with asyncio.TaskGroup() as tasks:
            for _ in range(concurrency):
                tasks.create_task(worker())
            cpu = tasks.create_task(measure_cpu())

    return dict(histogram), dict(errors), cpu.result()


def run_process(args: argparse.Namespace, concurrency: int, start: Barrier, results: Queue) -> None:
    results.put(run(load(args, concurrency, start), args.loop))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--protocol", choices=["tri", "dubbo"], default="tri")
    parser.add_argument("--url", help="the provider to call; 127.0.0.1:50051 over the protocol by default")
    parser.add_argument("--size", type=int, default=128, help="bytes of each request and response")
    parser.add_argument("--concurrency", type=int, default=16, help="calls in flight, over all processes")
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--duration", type=float, default=10.0, help="seconds counted")
    parser.add_argument("--warmup", type=float, default=3.0, help="seconds before counting")
    parser.add_argument("--loop", choices=["asyncio", "uvloop"], default="asyncio")
    args = parser.parse_args()
    args.url = args.url or f"{args.protocol}://127.0.0.1:50051"

    count = min(args.processes, args.concurrency)
    shares = [args.concurrency // count + (i < args.concurrency % count) for i in range(count)]
    context = get_context("spawn")
    start, results = context.Barrier(count + 1), context.Queue()
    processes = [context.Process(target=run_process, args=(args, share, start, results)) for share in shares]
    for process in processes:
        process.start()
    # A process that fails to connect never reaches the start, which then breaks.
    start.wait(timeout=60)
    print("started", flush=True)

    histogram: collections.Counter[int] = collections.Counter()
    errors: collections.Counter[str] = collections.Counter()
    cpu = 0.0
    for _ in processes:
        each_histogram, each_errors, each_cpu = results.get()
        histogram.update(each_histogram)
        errors.update(each_errors)
        cpu += each_cpu
    for process in processes:
        process.join()

    calls = sum(histogram.values())
    print(
        json.dumps(
            {
                "calls": calls,
                "errors": dict(errors),
                "rps": round(calls / args.duration, 1),
                "client_cpu_us": round(cpu / calls * 1e6, 2) if calls else None,
                "latency_us": percentiles(histogram),
                "histogram": {str(each): count for each, count in sorted(histogram.items())},
            }
        )
    )


if __name__ == "__main__":
    main()
