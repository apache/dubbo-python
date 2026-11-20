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

"""The services the benchmarks call, the same in every language: an echo of bytes over each protocol.

Also how the Python programs run on the event loop they are asked for.
"""

import asyncio
import typing
from collections.abc import Coroutine
from typing import Any

import dubbo

from bench_pb2 import Payload


# Triple carries the protobuf messages of bench.proto, which ghz and the Go server read too.
@dubbo.service("org.apache.dubbo.benchmark.Bench")
class Bench(typing.Protocol):
    @dubbo.method("Echo")
    async def echo(self, request: Payload) -> Payload: ...


# The Dubbo protocol carries Java types in Hessian 2, as the Java interface BenchService declares them.
@dubbo.service("org.apache.dubbo.benchmark.BenchService")
class BenchService(typing.Protocol):
    async def echo(self, data: bytes) -> bytes: ...


class BenchImpl(Bench):
    async def echo(self, request: Payload) -> Payload:
        return request


class BenchServiceImpl(BenchService):
    async def echo(self, data: bytes) -> bytes:
        return data


def run(main: Coroutine[Any, Any, Any], loop: str) -> Any:
    """Run ``main`` on the event loop named ``loop``: ``asyncio`` or ``uvloop``."""
    loop_factory = None
    if loop == "uvloop":
        import uvloop

        loop_factory = uvloop.new_event_loop
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(main)
