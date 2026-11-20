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

from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

import anyio

from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL

from .base import Filter

__all__ = ["ActiveCountFilter", "ActiveCounts", "active_counts"]

# The protocol, host, port, path and method of the calls counted together.
_Key = tuple[str, str | None, int | None, str, str]


class ActiveCounts:
    """The calls of each method under way, by the URL they go to.

    An application keeps the calls it makes to each provider in the
    ``ActiveCounts`` of its ``ApplicationScope.state``. A URL is told apart
    by its protocol, host, port and path, so that the counts outlive the
    invokers and filters made again for it, and the references of one
    application count their calls to one provider together.
    """

    def __init__(self) -> None:
        self._counts: Counter[_Key] = Counter()
        # Set as a call of the key ends, for the calls that wait for room.
        self._ended: dict[_Key, anyio.Event] = {}

    def get(self, url: URL, method: str) -> int:
        """Return the calls of ``method`` under way to ``url``."""
        return self._counts[_key(url, method)]

    async def wait_for_room(self, url: URL, method: str, limit: int) -> None:
        """Wait until fewer than ``limit`` calls of ``method`` are under way to ``url``.

        A call that counts as soon as this returns, before awaiting
        anything else, stays within ``limit``.
        """
        key = _key(url, method)
        while self._counts[key] >= limit:
            ended = self._ended.get(key)
            if ended is None:
                ended = self._ended[key] = anyio.Event()
            await ended.wait()

    @contextmanager
    def counting(self, url: URL, method: str) -> Generator[None]:
        """Count a call of ``method`` to ``url`` as under way until the block exits."""
        key = _key(url, method)
        self._counts[key] += 1
        try:
            yield
        finally:
            self._counts[key] -= 1
            if not self._counts[key]:
                del self._counts[key]
            ended = self._ended.pop(key, None)
            if ended is not None:
                ended.set()


class ActiveCountFilter(Filter):
    """Counts each call to the provider ``url`` as under way, in the ``ActiveCounts`` of its application, until it ends.

    A streaming call counts until it opens.

    Raises:
        RuntimeError: No application made ``url``.
    """

    def __init__(self, url: URL) -> None:
        self._counts = active_counts(url)
        self._url = url

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        with self._counts.counting(self._url, invocation.method):
            return await call_next(invocation)


def active_counts(url: URL) -> ActiveCounts:
    """Return the ``ActiveCounts`` of the calls the application that made ``url`` makes.

    Raises:
        RuntimeError: No application made ``url``.
    """
    return cast(ActiveCounts, url.scope.state.setdefault(ActiveCounts, ActiveCounts()))


def _key(url: URL, method: str) -> _Key:
    return url.protocol, url.host, url.port, url.path, method
