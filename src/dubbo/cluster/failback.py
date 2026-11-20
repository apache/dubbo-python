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
from contextlib import AsyncExitStack
from typing import Self

import anyio
from anyio.abc import TaskGroup

from dubbo.constants import FAILBACK_TASKS_KEY, RETRIES_KEY
from dubbo.exceptions import RemoteError
from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL

from .base import BaseCluster
from .directory import Directory

__all__ = ["FailbackCluster"]

_logger = logging.getLogger(__name__)

_RETRIES = 3
_TASKS = 100
_RETRY_INTERVAL = 5.0  # Seconds.


class FailbackCluster(BaseCluster):
    """Makes each call once and returns nothing instead of a failure, then makes the call again in the background.

    A unary call that fails other than with the error the method raised
    returns ``None``, and is made again every 5 seconds, on another
    candidate than the last when there is one, until it succeeds or has
    been made ``retries`` more times, 3 by default. At most
    ``failbacktasks`` calls, 100 by default, wait to be made again; beyond
    them a failed call is dropped. Closing the cluster drops those waiting.
    A streaming call returns how it opened.

    Raises:
        ValueError: ``retries`` is negative or ``failbacktasks`` is not positive.
    """

    def __init__(self, url: URL, directory: Directory) -> None:
        super().__init__(url, directory)
        self._retries = url.get_parameter(RETRIES_KEY, int, _RETRIES)
        self._tasks = url.get_parameter(FAILBACK_TASKS_KEY, int, _TASKS)
        if self._retries < 0 or self._tasks <= 0:
            raise ValueError(f"{RETRIES_KEY} must not be negative and {FAILBACK_TASKS_KEY} must be positive")
        self._waiting = 0
        self._stack = AsyncExitStack()
        # Set once entered; makes the failed calls again.
        self._task_group: TaskGroup | None = None

    async def aclose(self) -> None:
        try:
            await self._stack.aclose()
        finally:
            await super().aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            task_group = self._task_group = await stack.enter_async_context(anyio.create_task_group())
            stack.callback(task_group.cancel_scope.cancel)
            self._stack = stack.pop_all()

        return self

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        invoker = self._select(invokers, invocation)
        result = await invoker.invoke(invocation)
        if not _failed(result) or invocation.definition.rpc_type is not RpcType.UNARY:
            return result

        if self._task_group is None:
            raise RuntimeError("the failback cluster is not open")
        if not self._retries:
            _logger.warning("A call of %s.%s failed; it returns None", *_name(invocation), exc_info=result.error)
        elif self._waiting >= self._tasks:
            _logger.error(
                "A call of %s.%s failed while %d others wait to be made again; it returns None and is dropped",
                *_name(invocation),
                self._waiting,
                exc_info=result.error,
            )
        else:
            _logger.warning(
                "A call of %s.%s failed; it returns None and is made again in the background",
                *_name(invocation),
                exc_info=result.error,
            )
            self._waiting += 1
            self._task_group.start_soon(self._retry, invocation, invoker)
        return Result()

    async def _retry(self, invocation: Invocation, last: Invoker) -> None:
        try:
            for _ in range(self._retries):
                await anyio.sleep(_RETRY_INTERVAL)
                invokers = self.directory.candidates(invocation)
                if not invokers:
                    continue
                last = self._select([invoker for invoker in invokers if invoker is not last] or invokers, invocation)
                if not _failed(await last.invoke(invocation)):
                    return
            _logger.error("A call of %s.%s failed %d more times; it is dropped", *_name(invocation), self._retries)
        except Exception:
            _logger.exception("A call of %s.%s failed to be made again; it is dropped", *_name(invocation))
        finally:
            self._waiting -= 1


def _failed(result: Result) -> bool:
    return result.error is not None and not isinstance(result.error, RemoteError)


def _name(invocation: Invocation) -> tuple[str, str]:
    return invocation.interface, invocation.method
