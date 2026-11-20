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

from typing import cast

from dubbo.constants import EXECUTES_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL

from .activecount import ActiveCounts
from .base import Filter

__all__ = ["ExecutesFilter"]


class ExecutesFilter(Filter):
    """Fails with ``UNAVAILABLE`` the calls of a method beyond those the service ``url`` may serve at once.

    The limit of a method is ``{method}.executes``, else ``executes``; 0
    or less means no limit. Every call counts as under way in the
    ``ActiveCounts`` of the calls the application serves, apart from those
    it makes, so that a limit the override rules lower refuses new calls
    until those under way end within it.

    Raises:
        RuntimeError: No application made ``url``.
    """

    def __init__(self, url: URL) -> None:
        self._counts = _served_counts(url)
        self._url = url
        self._default = url.get_parameter(EXECUTES_KEY, int, 0)
        self._limits = url.get_method_parameters(EXECUTES_KEY, int)

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        method = invocation.method
        limit = self._limits.get(method, self._default)
        if limit > 0 and self._counts.get(self._url, method) >= limit:
            error = RpcError(
                Status.UNAVAILABLE, f"{invocation.interface}.{invocation.method} serves {limit} calls at once"
            )
            return Result(error=error)

        with self._counts.counting(self._url, method):
            return await call_next(invocation)


def _served_counts(url: URL) -> ActiveCounts:
    return cast(ActiveCounts, url.scope.state.setdefault((ExecutesFilter, ActiveCounts), ActiveCounts()))
