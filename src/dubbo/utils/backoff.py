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

"""Waits between attempts that fail."""

import random
from collections.abc import Iterator

__all__ = ["backoff"]


def backoff(first: float = 1.0, longest: float = 30.0) -> Iterator[float]:
    """Yield the seconds to wait before each next attempt, from ``first`` doubling up to ``longest``, each with jitter."""
    delay = first
    while True:
        yield random.uniform(delay / 2, delay)
        delay = min(delay * 2, longest)
