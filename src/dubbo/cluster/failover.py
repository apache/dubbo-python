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

from dubbo.constants import DEFAULT_RETRIES, RETRIES_KEY
from dubbo.exceptions import RemoteError, RpcError, Status
from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL

from .base import BaseCluster
from .directory import Directory

__all__ = ["FailoverCluster"]


class FailoverCluster(BaseCluster):
    """Retries a unary call that fails with ``UNAVAILABLE`` on a provider it has not tried, while any remains.

    A call makes at most ``{method}.retries``, else ``retries``, else 2
    attempts after the first. A streaming call makes one attempt. Each
    retry asks the directory for the candidates again; when none is left,
    the call ends with the last failure.
    """

    def __init__(self, url: URL, directory: Directory) -> None:
        super().__init__(url, directory)
        self._attempts = url.get_parameter(RETRIES_KEY, int, DEFAULT_RETRIES) + 1
        self._method_attempts = {
            method: retries + 1 for method, retries in url.get_method_parameters(RETRIES_KEY, int).items()
        }

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        attempts = self._get_attempts(invocation)
        tried: list[Invoker] = []
        candidates = invokers
        while True:
            invoker = self._select(candidates, invocation)
            result = await invoker.invoke(invocation)
            attempts -= 1
            if attempts <= 0 or not _retryable(result):
                return result

            tried.append(invoker)
            invokers = self.directory.candidates(invocation)
            if not invokers:
                return result

            candidates = tuple(other for other in invokers if other not in tried) or invokers

    def _get_attempts(self, invocation: Invocation) -> int:
        if invocation.definition.rpc_type is not RpcType.UNARY:
            return 1

        return self._method_attempts.get(invocation.method, self._attempts)


def _retryable(result: Result) -> bool:
    # A RemoteError is the answer of the method, which a retry would run again.
    error = result.error
    return isinstance(error, RpcError) and not isinstance(error, RemoteError) and error.status is Status.UNAVAILABLE
