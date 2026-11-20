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

from collections.abc import Sequence
from contextlib import AsyncExitStack
from typing import Self

from dubbo.rpc.invocation import Invocation, Invoker

from ..router import Router, RouterChain
from .base import Directory

__all__ = ["StaticDirectory"]


class StaticDirectory(Directory):
    """A fixed set of invokers, which closing it closes.

    It owns ``routers``, which act as one ``RouterChain``: entering ``async
    with`` opens them and gives them the invokers, they narrow the
    candidates of each call in turn, and they close first.
    """

    def __init__(self, invokers: Sequence[Invoker], routers: Sequence[Router] = ()) -> None:
        self._invokers = tuple(invokers)
        self._chain = RouterChain(routers)

    @property
    def available(self) -> bool:
        return any(invoker.available for invoker in self._invokers)

    def candidates(self, invocation: Invocation) -> Sequence[Invoker]:
        return self._chain.route(self._invokers, invocation)

    async def aclose(self) -> None:
        async with AsyncExitStack() as stack:
            for invoker in self._invokers:
                stack.push_async_callback(invoker.aclose)
            stack.push_async_callback(self._chain.aclose)

    async def __aenter__(self) -> Self:
        await self._chain.__aenter__()
        self._chain.notify(self._invokers)
        return self
