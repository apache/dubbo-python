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

import bisect
import hashlib
from collections.abc import Sequence

from dubbo.constants import HASH_ARGUMENTS_KEY, HASH_NODES_KEY
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import URL
from dubbo.utils.converters import to_text

from .base import LoadBalance, PerSequence

__all__ = ["ConsistentHashLoadBalance"]

_NODES = 160
_ARGUMENTS = (0,)


class ConsistentHashLoadBalance(LoadBalance):
    """Chooses the provider that the arguments of a call hash to, so that equal arguments go to the same provider.

    It is ketama consistent hashing over a ring of 32-bit points. Each
    provider owns ``{method}.hash.nodes``, else ``hash.nodes``, else 160
    points: for ``i`` from 0 up to a quarter of them, the MD5 digest of its
    address followed by ``i``, as in ``10.0.0.1:20880`` and ``0``, read as
    four little-endian integers; of two providers on one point, the later
    keeps it. A call goes to the owner of the first point at or after the
    first such integer of the MD5 digest of its key, wrapping around. The
    key is the arguments at the indexes ``{method}.hash.arguments``, else
    ``hash.arguments``, else ``0``, separated by commas, as text one after
    the other, ``None`` as ``null`` and booleans as ``true`` and ``false``;
    an index beyond the arguments adds nothing. Weights play no part. A ring
    is built for each sequence of invokers a `PerSequence` keeps.

    Raises:
        ValueError: ``hash.nodes`` is below 4, or ``hash.arguments`` holds
            something other than integers.
    """

    def __init__(self, url: URL) -> None:
        self._nodes = url.get_parameter(HASH_NODES_KEY, int, _NODES)
        self._method_nodes = url.get_method_parameters(HASH_NODES_KEY, int)
        if min([self._nodes, *self._method_nodes.values()]) < 4:
            raise ValueError(f"{HASH_NODES_KEY} must be at least 4")
        self._arguments = url.get_parameter(HASH_ARGUMENTS_KEY, _indexes, _ARGUMENTS)
        self._method_arguments = url.get_method_parameters(HASH_ARGUMENTS_KEY, _indexes)
        self._rings = PerSequence(lambda invokers, method: _Ring(invokers, self._method_nodes.get(method, self._nodes)))

    def select(self, invokers: Sequence[Invoker], invocation: Invocation) -> Invoker:
        if len(invokers) == 1:
            return invokers[0]

        method = invocation.method
        arguments = invocation.arguments
        indexes = self._method_arguments.get(method, self._arguments)
        key = "".join(to_text(arguments[index]) for index in indexes if 0 <= index < len(arguments))
        return self._rings.get(invokers, method).get(key)


class _Ring:
    """The points of the providers on the ring, in order, and the owner of each."""

    def __init__(self, invokers: Sequence[Invoker], nodes: int) -> None:
        owners: dict[int, Invoker] = {}
        for invoker in invokers:
            address = invoker.url.address
            for index in range(nodes // 4):
                digest = _md5(f"{address}{index}")
                for number in range(4):
                    owners[_point(digest, number)] = invoker

        self._points = sorted(owners)
        self._owners = [owners[point] for point in self._points]

    def get(self, key: str) -> Invoker:
        """Return the owner of the first point at or after the point of ``key``, wrapping around."""
        index = bisect.bisect_left(self._points, _point(_md5(key), 0))
        return self._owners[index % len(self._points)]


def _md5(text: str) -> bytes:
    return hashlib.md5(text.encode(), usedforsecurity=False).digest()


def _point(digest: bytes, number: int) -> int:
    return int.from_bytes(digest[number * 4 : number * 4 + 4], "little")


def _indexes(value: str) -> tuple[int, ...]:
    return tuple(int(index) for index in value.split(","))
