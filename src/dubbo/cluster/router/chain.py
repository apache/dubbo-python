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

from dubbo.extension import Resource
from dubbo.rpc.invocation import Invocation, Invoker

from .base import Router

__all__ = ["RouterChain"]


class RouterChain(Resource):
    """Routers that act as one ``Router``: each takes every set of providers whole, and routes a call among what those before it left.

    Without routers, a call may go to every provider. Entering ``async with``
    opens the routers in order, and closing closes them in reverse.
    """

    def __init__(self, routers: Sequence[Router] = ()) -> None:
        self._routers = tuple(routers)
        self._stack = AsyncExitStack()

    def notify(self, invokers: Sequence[Invoker]) -> None:
        """Tell every router of the providers, which changed."""
        for router in self._routers:
            router.notify(invokers)

    def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        """Return those of ``invokers`` that every router, in turn, lets ``invocation`` go to."""
        for router in self._routers:
            invokers = router.route(invokers, invocation)
        return invokers

    async def aclose(self) -> None:
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            for router in self._routers:
                await stack.enter_async_context(router)  # ty: ignore[invalid-argument-type]
            self._stack = stack.pop_all()

        return self
