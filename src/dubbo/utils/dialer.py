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

"""The attempts of one client to connect to its peer."""

import asyncio
import copy
from collections.abc import Callable, Coroutine
from typing import Any, Generic, TypeVar

from .backoff import backoff

__all__ = ["Dialer"]

T = TypeVar("T")


class Dialer(Generic[T]):
    """Connects one client to its peer: one attempt at a time, and again after a backoff once one fails or the connection is lost.

    ``connect`` opens a connection, bounded by the connect timeout, and
    returns it. An attempt belongs to the dialer, not to the callers waiting
    for it: one that stops waiting leaves it to the others, and only closing
    cancels it.

    The dialer is connected from an attempt that succeeds until the
    connection is lost, an attempt fails or it closes; before its first
    attempt succeeds, it is not.
    """

    def __init__(self, connect: Callable[[], Coroutine[Any, Any, T]]) -> None:
        self._connect = connect
        self._attempt: asyncio.Task[T] | None = None
        self._retry: asyncio.TimerHandle | None = None
        self._delays = backoff()
        self._connected = False
        self._closed = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        """Start an attempt in the background unless one is under way."""
        if self._attempt is None and not self._closed:
            self._start()

    async def connect(self) -> T | None:
        """Return what the attempt under way connects, starting one at once if none is, even during a backoff.

        Returns ``None`` once the dialer is closed.

        Raises:
            Exception: A copy of what the attempt raised.
        """
        if self._closed:
            return None
        attempt = self._attempt or self._start()

        await asyncio.wait((attempt,))
        if attempt.cancelled():
            return None
        error = attempt.exception()
        if error is not None:
            # Each waiter raises its own copy, so that the shared one gathers no traceback; one that cannot be copied
            # is raised itself.
            try:
                raised = copy.copy(error)
            except Exception:
                raised = error
            raise raised from error.__cause__
        return attempt.result()

    def lost(self) -> None:
        """Connect again after the next backoff, as the connection has been lost or an attempt failed.

        A loss while an attempt is under way leaves connecting again to that attempt.
        """
        if self._closed:
            return
        self._connected = False
        if self._attempt is not None:
            return
        if self._retry is not None:
            self._retry.cancel()
        self._retry = asyncio.get_running_loop().call_later(next(self._delays), self._start)

    def close(self) -> None:
        """Stop for good: cancel the retry pending and the attempt under way."""
        self._closed, self._connected = True, False
        if self._retry is not None:
            self._retry.cancel()
        if self._attempt is not None:
            self._attempt.cancel()

    async def aclose(self) -> None:
        """Close, and wait for the attempt under way to end."""
        attempt = self._attempt
        self.close()
        if attempt is not None:
            await asyncio.wait((attempt,))

    def _start(self) -> asyncio.Task[T]:
        if self._retry is not None:
            self._retry.cancel()
            self._retry = None
        attempt = self._attempt = asyncio.get_running_loop().create_task(self._run())
        # An attempt nobody waits for fails quietly; the next one follows the backoff.
        attempt.add_done_callback(lambda attempt: attempt.cancelled() or attempt.exception())
        return attempt

    async def _run(self) -> T:
        # The attempt is over once the connection is returned, so that a loss reported from then on starts the next.
        try:
            connection = await self._connect()
        except Exception:
            self._attempt = None
            self.lost()
            raise
        finally:
            self._attempt = None

        self._connected = True
        self._delays = backoff()
        return connection
