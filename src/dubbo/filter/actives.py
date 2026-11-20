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

import anyio

from dubbo.constants import ACTIVES_KEY, TIMEOUT_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL
from dubbo.utils.converters import milliseconds

from .activecount import active_counts
from .base import Filter

__all__ = ["ActivesFilter"]


class ActivesFilter(Filter):
    """Holds the calls of a method beyond those that may go to the provider ``url`` at once, until one of them ends.

    The limit of a method is ``{method}.actives``, else ``actives``; 0 or
    less means no limit. A held call waits up to the timeout of its method,
    ``{method}.timeout``, else ``timeout``, else without end, then fails
    with ``UNAVAILABLE``. Every call counts as under way in the
    ``ActiveCounts`` of the application, as ``ActiveCountFilter`` counts, so
    that the limit holds across the invokers made again for the provider
    and across the references of the application. A streaming call counts
    until it opens.

    Raises:
        RuntimeError: No application made ``url``.
    """

    def __init__(self, url: URL) -> None:
        self._counts = active_counts(url)
        self._url = url
        self._default = url.get_parameter(ACTIVES_KEY, int, 0)
        self._limits = url.get_method_parameters(ACTIVES_KEY, int)
        self._timeout = url.get_parameter(TIMEOUT_KEY, milliseconds, None)
        self._timeouts = url.get_method_parameters(TIMEOUT_KEY, milliseconds)

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        method = invocation.method
        limit = self._limits.get(method, self._default)
        if limit > 0:
            timeout = self._timeouts.get(method, self._timeout)
            with anyio.move_on_after(timeout) as scope:
                await self._counts.wait_for_room(self._url, method, limit)
            if scope.cancelled_caught:
                error = RpcError(
                    Status.UNAVAILABLE,
                    f"{invocation.interface}.{method} makes {limit} calls at once to {self._url.address},"
                    f" and none ended within {timeout} seconds",
                )
                return Result(error=error)

        with self._counts.counting(self._url, method):
            return await call_next(invocation)
