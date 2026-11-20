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

from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL

from .base import LoadBalance, PerSequence, Weights

__all__ = ["RoundRobinLoadBalance"]


class RoundRobinLoadBalance(LoadBalance):
    """Chooses the providers in turn, each as often as its weight, spread out as evenly as they can be.

    It is the smooth weighted round robin of nginx: on each call every
    provider gains its weight, the one with the most is chosen, and it loses
    the total of the weights. Providers of weights 5, 1 and 1 are chosen in
    the order a, a, b, a, c, a, a. The weights are those of ``Weights``; a
    provider of weight 0 is never chosen, unless all weigh 0, when they take
    turns. Each sequence of invokers a `PerSequence` keeps takes turns of
    its own, so that each of the sets of providers routing alternates
    between is spread evenly. A new sequence starts from the turns of the
    one started before it, so that a provider keeps its place while the
    invokers change, and starts at none when it joins them.
    """

    def __init__(self, url: URL) -> None:
        self._weights = Weights()
        # What each invoker of a sequence has gained.
        self._gains = PerSequence(self._start)
        # By method: the sequence started last, and its gains.
        self._last: dict[str, tuple[Sequence[Invoker], list[int]]] = {}

    def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        if len(invokers) == 1:
            return invokers[0]

        method = invocation.method
        weights = self._weights.get(invokers, method)
        gains = self._gains.get(invokers, method)
        chosen = _take_turn(gains, weights)
        if chosen < 0:
            chosen = _take_turn(gains, [1] * len(gains))
        return invokers[chosen]

    def _start(self, invokers: Sequence[Invoker], method: str) -> list[int]:
        """Return the gains of ``invokers``, those of the sequence started last for the invokers it holds."""
        last, gains = self._last.get(method, ((), []))
        # By identity, since invokers need not be hashable.
        kept = {id(invoker): gain for invoker, gain in zip(last, gains, strict=True)}
        gains = [kept.get(id(invoker), 0) for invoker in invokers]
        self._last[method] = (invokers, gains)
        return gains


def _take_turn(gains: list[int], weights: list[int]) -> int:
    """Add ``weights`` to ``gains``, take their total from the greatest, and return its index, or -1 if all weigh 0."""
    chosen = -1
    total = 0
    for index, weight in enumerate(weights):
        if weight:
            gains[index] += weight
            total += weight
            if chosen < 0 or gains[index] > gains[chosen]:
                chosen = index

    if chosen >= 0:
        gains[chosen] -= total
    return chosen
