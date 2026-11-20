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

import math

__all__ = ["BDP_PING", "MAX_WINDOW", "BdpEstimator"]

# The opaque data of a measuring PING; keep-alive PINGs count up from 1 and in practice never reach it.
BDP_PING = b"\xff" * 8

MAX_WINDOW = 16 * 1024 * 1024
# libnghttp2 returns credit once half the window is consumed. A whole number of pairs of default-sized
# DATA frames keeps that half on a frame boundary, so the peer can keep the entire window in flight.
_WINDOW_STEP = 2 * 16 * 1024
_GROWTH_THRESHOLD = 2 / 3
_RTT_WEIGHT = 0.125
_MAX_BACKOFF = 10


class BdpEstimator:
    """Grows the initial stream window to twice the credit returned in a round trip, timed with PING.

    Credit is returned in bursts paced by the round trip, and the acknowledgement
    of a probe arrives just before the burst its WINDOW_UPDATE released. The
    credit returned between two acknowledgements therefore spans whole bursts;
    as a rate over that span times the smoothed round trip, measured from the
    write of each PING, it is the sample. The window grows to twice the sample,
    in whole steps of two default-sized frames and at most `MAX_WINDOW`, when
    the sample fills two thirds of it and the rate is the fastest that has
    grown it.

    A probe starts when credit is returned after DATA has arrived since the
    previous acknowledgement, so the peer has written between any two probes.
    Probes that grow nothing make the next one wait for more credit, up to ten
    times half the window. An acknowledgement no written probe waits for
    changes nothing.

    ``window`` is the initial stream window the connection starts with.

    Attributes:
        data_received: Whether DATA has arrived since the last acknowledgement;
            the connection sets it for each DATA frame.
        probe_unwritten: Whether the PING of the current probe is queued and
            not yet written; the connection reports the write with
            `probe_written`.
    """

    def __init__(self, window: int) -> None:
        self.window = window
        self.data_received = False
        self.probe_unwritten = False

        self._probing = False
        self._sent_at: float | None = None
        self._acknowledged_at: float | None = None
        self._rtt = 0.0
        self._best_rate = 0.0
        self._backoff = 0
        # Credit returned since the last acknowledgement, and the part the next probe waits for.
        self._returned = 0
        self._threshold = 0

    @property
    def finished(self) -> bool:
        """Return whether the window has reached `MAX_WINDOW`."""
        return self.window >= MAX_WINDOW

    def credit_returned(self, amount: int) -> bool:
        """Record returned credit, and return whether to queue the PING of a probe that starts now."""
        self._returned += amount
        if self._probing or not self.data_received or self._returned < self._threshold:
            return False

        self._probing = True
        self.probe_unwritten = True
        self._sent_at = None
        return True

    def probe_written(self, now: float) -> None:
        """Start the round trip of the current probe at ``now``, when its PING is written."""
        self.probe_unwritten = False
        self._sent_at = now

    def probe_acknowledged(self, now: float) -> int | None:
        """Finish the probe and return the new window, or None when it stays."""
        sent_at = self._sent_at
        if not self._probing or sent_at is None:
            return None

        rtt = now - sent_at
        span = now - (sent_at if self._acknowledged_at is None else self._acknowledged_at)
        returned = self._returned

        self._probing = False
        self.data_received = False
        self._acknowledged_at = now
        self._returned = 0
        if rtt <= 0 or span <= 0:
            return None

        self._rtt = rtt if not self._rtt else self._rtt + (rtt - self._rtt) * _RTT_WEIGHT
        window = self._grow(returned / span)
        self._backoff = 0 if window is not None else min(self._backoff + 1, _MAX_BACKOFF)
        self._threshold = self._backoff * self.window // 2
        return window

    def _grow(self, rate: float) -> int | None:
        sample = rate * self._rtt
        target = min(math.ceil(2 * sample / _WINDOW_STEP) * _WINDOW_STEP, MAX_WINDOW)
        if rate < self._best_rate or sample < _GROWTH_THRESHOLD * self.window or target <= self.window:
            return None

        self._best_rate = rate
        self.window = target
        return target
