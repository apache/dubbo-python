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

import pytest

from dubbo.transport.h2.aio.bdp import MAX_WINDOW, BdpEstimator

pytestmark = pytest.mark.anyio

_WINDOW = 65536

_RTT = 0.01


def _probe(estimator: BdpEstimator, returned: int, *, at: float = 0.0, rtt: float = _RTT) -> int | None:
    """Return ``returned`` credit after DATA, writing the PING it queues at ``at`` and acknowledging it ``rtt`` later."""
    estimator.data_received = True
    assert estimator.credit_returned(returned)
    estimator.probe_written(at)
    return estimator.probe_acknowledged(at + rtt)


def test_a_window_that_limits_the_flow_grows_to_twice_the_sample_in_pairs_of_frames() -> None:
    estimator = BdpEstimator(_WINDOW)

    # Twice 60000 rounds up to four pairs of 16 KiB frames.
    assert _probe(estimator, 60000) == 131072
    assert estimator.window == 131072


def test_credit_returned_slowly_grows_nothing() -> None:
    assert _probe(BdpEstimator(_WINDOW), 10000) is None


def test_the_sample_is_the_credit_between_acknowledgements_wherever_the_probe_starts() -> None:
    estimator = BdpEstimator(_WINDOW)
    assert _probe(estimator, 60000) == 131072

    # Half the next burst returns before DATA allows a probe; it still belongs to the sample.
    assert not estimator.credit_returned(50000)
    estimator.data_received = True
    assert estimator.credit_returned(50000)
    estimator.probe_written(_RTT + 0.005)

    # 100000 bytes over the 10 ms since the last acknowledgement, times the smoothed 9.375 ms round trip.
    assert estimator.probe_acknowledged(2 * _RTT) == 196608


def test_the_round_trip_starts_when_the_ping_is_written() -> None:
    estimator = BdpEstimator(_WINDOW)
    estimator.data_received = True
    assert estimator.credit_returned(60000)

    # The PING waits a second behind paused writes; that wait is not part of the round trip.
    estimator.probe_written(1.0)
    assert estimator.probe_acknowledged(1.0 + _RTT) == 131072


def test_an_acknowledgement_no_written_probe_waits_for_changes_nothing() -> None:
    estimator = BdpEstimator(_WINDOW)
    assert estimator.probe_acknowledged(100.0) is None

    estimator.data_received = True
    assert estimator.credit_returned(60000)
    assert estimator.probe_acknowledged(100.0) is None

    estimator.probe_written(200.0)
    assert estimator.probe_acknowledged(200.0 + _RTT) == 131072


def test_a_slower_rate_does_not_grow_the_window() -> None:
    estimator = BdpEstimator(_WINDOW)
    assert _probe(estimator, 60000) == 131072

    # More bytes over a much longer span: the window is not what limits the flow.
    assert _probe(estimator, 100000, at=1.0) is None


def test_a_fast_probe_that_grows_nothing_leaves_slower_growth_possible() -> None:
    estimator = BdpEstimator(_WINDOW)
    # 40000 bytes in 10 ms is fast, but fills less than two thirds of the window.
    assert _probe(estimator, 40000) is None

    # The round trip lengthens and a slower flow now fills the window.
    assert _probe(estimator, 300000, at=_RTT, rtt=0.1) == 131072


def test_no_probe_starts_before_data_arrives_after_the_last_acknowledgement() -> None:
    estimator = BdpEstimator(_WINDOW)
    assert not estimator.credit_returned(100)

    _probe(estimator, 60000)
    assert not estimator.credit_returned(10 * MAX_WINDOW)

    estimator.data_received = True
    assert estimator.credit_returned(1)


def test_probes_that_grow_nothing_wait_for_more_credit() -> None:
    estimator = BdpEstimator(_WINDOW)
    assert _probe(estimator, 10000) is None
    assert _probe(estimator, 40000, at=1.0) is None

    # Two probes grew nothing: the next waits for credit of one window since the acknowledgement.
    estimator.data_received = True
    assert not estimator.credit_returned(_WINDOW // 2)
    assert estimator.credit_returned(_WINDOW // 2)


def test_the_window_stops_at_the_cap_and_tuning_finishes() -> None:
    estimator = BdpEstimator(MAX_WINDOW // 2)

    assert _probe(estimator, MAX_WINDOW) == MAX_WINDOW
    assert estimator.finished
