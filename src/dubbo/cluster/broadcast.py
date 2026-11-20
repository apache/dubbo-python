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

import logging
from collections.abc import Sequence

from dubbo.constants import BROADCAST_FAIL_PERCENT_KEY
from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL

from .base import BaseCluster, available_invokers
from .directory import Directory

__all__ = ["BroadcastCluster"]

_logger = logging.getLogger(__name__)


class BroadcastCluster(BaseCluster):
    """Makes a unary call on every invoker, one after another, and returns the last failure, else the last result.

    Any error counts as a failure, the method's own too. The calls stop
    once ``broadcast.fail.percent`` percent of the invokers, rounded down,
    have failed; 100, the default, and 0 call all of them. A streaming call
    is made once, on the invoker the load balance chooses.

    Raises:
        ValueError: ``broadcast.fail.percent`` is not between 0 and 100.
    """

    def __init__(self, url: URL, directory: Directory) -> None:
        super().__init__(url, directory)
        self._fail_percent = url.get_parameter(BROADCAST_FAIL_PERCENT_KEY, int, 100)
        if not 0 <= self._fail_percent <= 100:
            raise ValueError(f"{BROADCAST_FAIL_PERCENT_KEY} must be between 0 and 100, not {self._fail_percent}")

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        if invocation.definition.rpc_type is not RpcType.UNARY:
            return await self._select(invokers, invocation).invoke(invocation)

        invokers = available_invokers(invokers)
        failures_allowed = len(invokers) * self._fail_percent // 100 or len(invokers)
        failure: Result | None = None
        failures = 0
        for invoker in invokers:
            result = await invoker.invoke(invocation)
            if result.error is None:
                continue

            _logger.warning(
                "Broadcasting %s.%s to %s failed",
                invocation.interface,
                invocation.method,
                invoker.url,
                exc_info=result.error,
            )
            failure = result
            failures += 1
            if failures == failures_allowed:
                break

        return failure or result
