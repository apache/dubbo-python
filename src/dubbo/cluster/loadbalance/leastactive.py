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

import random
from collections.abc import Sequence

from dubbo.filter.activecount import active_counts
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL

from .base import LoadBalance, Weights

__all__ = ["LeastActiveLoadBalance"]


class LeastActiveLoadBalance(LoadBalance):
    """Chooses the provider with the fewest calls of the method under way, among those tied at random by weight.

    The weights are those of ``Weights``; a provider of weight 0 is never
    chosen, unless all weigh 0, when they weigh the same. The calls under
    way are those the application makes, in the ``ActiveCounts`` of its
    scope, which the filter of each attempt on a provider counts while this
    load balance is set.

    Raises:
        RuntimeError: No application made the URL of the reference.
    """

    def __init__(self, url: URL) -> None:
        self._counts = active_counts(url)
        self._weights = Weights()

    def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        if len(invokers) == 1:
            return invokers[0]

        method = invocation.method
        weights = self._weights.get(invokers, method)
        if not any(weights):
            weights = [1] * len(invokers)

        least: list[Invoker] = []
        least_weights: list[int] = []
        least_active = 0
        for invoker, weight in zip(invokers, weights, strict=True):
            if not weight:
                continue
            active = self._counts.get(invoker.url, method)
            if not least or active < least_active:
                least, least_weights, least_active = [invoker], [weight], active
            elif active == least_active:
                least.append(invoker)
                least_weights.append(weight)

        if len(least) == 1:
            return least[0]
        return random.choices(least, weights=least_weights)[0]
