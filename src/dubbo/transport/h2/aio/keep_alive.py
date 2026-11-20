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

import asyncio
from collections.abc import Callable

__all__ = ["KeepAlive"]

_MAX_PING_ID = 0xFFFFFFFFFFFFFFFF


class KeepAlive:
    """Probes a connection with PING after a quiet interval and expires it when no acknowledgement arrives.

    Inbound bytes of any kind count as activity. One timer runs at a time: the
    idle deadline, or while a PING is outstanding, its acknowledgement deadline.

    Args:
        loop: The connection's event loop.
        interval: Seconds without inbound bytes before a PING is sent.
        timeout: Seconds to wait for the PING's acknowledgement.
        ping: Sends a PING with the given 8-byte payload.
        expire: Called when the acknowledgement does not arrive in time.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        interval: float,
        timeout: float,
        ping: Callable[[bytes], None],
        expire: Callable[[], None],
    ) -> None:
        self._loop = loop
        self._interval = interval
        self._timeout = timeout
        self._ping = ping
        self._expire = expire

        self._last_received = loop.time()
        self._ping_id = 0
        self._outstanding: bytes | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._stopped = False

        self._arm_idle()

    def received(self) -> None:
        """Record inbound activity, which postpones the next PING."""
        # The hot path only stores the time; the idle timer rechecks it when it fires.
        self._last_received = self._loop.time()

    def acknowledged(self, payload: bytes) -> None:
        """Complete the outstanding PING if ``payload`` matches it."""
        if payload != self._outstanding:
            return

        self._outstanding = None
        self._arm_idle()

    def stop(self) -> None:
        """Stop probing for good."""
        self._stopped = True
        self._outstanding = None
        self._cancel_timer()

    def _arm_idle(self) -> None:
        self._cancel_timer()
        if not self._stopped:
            self._timer = self._loop.call_at(self._last_received + self._interval, self._on_idle)

    def _on_idle(self) -> None:
        self._timer = None
        if self._stopped:
            return

        deadline = self._last_received + self._interval
        if deadline > self._loop.time():
            self._timer = self._loop.call_at(deadline, self._on_idle)
            return

        self._ping_id = (self._ping_id + 1) & _MAX_PING_ID
        self._outstanding = self._ping_id.to_bytes(8, "big")
        # Armed first, so a ping that fails and stops probing also cancels it.
        self._timer = self._loop.call_later(self._timeout, self._on_timeout)
        self._ping(self._outstanding)

    def _on_timeout(self) -> None:
        self._timer = None
        if self._outstanding is not None and not self._stopped:
            self._expire()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
