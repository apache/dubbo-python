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

import itertools
import random
from collections.abc import Sequence

from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL

from .base import LoadBalance, Weights

__all__ = ["RandomLoadBalance"]


class RandomLoadBalance(LoadBalance):
    """Chooses a provider at random, in proportion to its weight.

    The weights are those of ``Weights``. When all invokers weigh the same,
    or all weigh 0, each is equally likely.
    """

    def __init__(self, url: URL) -> None:
        self._weights = Weights()
        # By method: the weights the running totals were computed from, and the totals, None when all are equal.
        self._cum_weights: dict[str, tuple[list[int], list[int] | None]] = {}

    def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        if len(invokers) == 1:
            return invokers[0]

        method = invocation.method
        weights = self._weights.get(invokers, method)
        weighed, cum_weights = self._cum_weights.get(method, (None, None))
        if weights is not weighed:
            cum_weights = _cum_weights(weights)
            self._cum_weights[method] = (weights, cum_weights)

        if cum_weights is None:
            return random.choice(invokers)

        return random.choices(invokers, cum_weights=cum_weights)[0]


def _cum_weights(weights: list[int]) -> list[int] | None:
    if len(set(weights)) == 1:
        return None

    return list(itertools.accumulate(weights))
