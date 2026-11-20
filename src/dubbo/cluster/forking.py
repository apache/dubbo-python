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

import anyio

from dubbo.constants import DEFAULT_FORKS, FORKS_KEY
from dubbo.exceptions import RemoteError
from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL

from .base import BaseCluster, available_invokers
from .directory import Directory

__all__ = ["ForkingCluster"]


class ForkingCluster(BaseCluster):
    """Makes a unary call on several invokers at once and returns the first answer, cancelling the other calls.

    It calls ``forks`` invokers, 2 by default, that the load balance chooses
    one after another, or all the available ones when ``forks`` is not below
    their number or not positive. An answer is a result without an error or
    with the error the method raised; when none answers, the call ends with
    the last failure. A streaming call is made once, on the invoker the load
    balance chooses.
    """

    def __init__(self, url: URL, directory: Directory) -> None:
        super().__init__(url, directory)
        self._forks = url.get_parameter(FORKS_KEY, int, DEFAULT_FORKS)

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        if invocation.definition.rpc_type is not RpcType.UNARY:
            return await self._select(invokers, invocation).invoke(invocation)

        chosen = self._choose(invokers, invocation)
        if len(chosen) == 1:
            return await chosen[0].invoke(invocation)

        results: list[Result] = []
        async with anyio.create_task_group() as task_group:

            async def call(invoker: Invoker) -> None:
                result = await invoker.invoke(invocation)
                results.append(result)
                if _answered(result):
                    task_group.cancel_scope.cancel()

            for invoker in chosen:
                task_group.start_soon(call, invoker)

        answers = [result for result in results if _answered(result)]
        return answers[0] if answers else results[-1]

    def _choose(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        if not 0 < self._forks < len(invokers):
            return available_invokers(invokers)

        chosen: list[Invoker] = []
        remaining = invokers
        while len(chosen) < self._forks:
            invoker = self._select(remaining, invocation)
            chosen.append(invoker)
            # A new sequence, since a load balance may keep what it derived from one by identity.
            remaining = tuple(other for other in remaining if other is not invoker)
        return chosen


def _answered(result: Result) -> bool:
    return result.error is None or isinstance(result.error, RemoteError)
