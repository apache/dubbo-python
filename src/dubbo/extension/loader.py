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

from collections.abc import Callable
from functools import cache
from importlib import metadata
from typing import ParamSpec, TypeVar, cast

from .exceptions import ExtensionError

__all__ = ["Extensions", "extension_point", "extensions"]

P = ParamSpec("P")
T = TypeVar("T")

_Entry = metadata.EntryPoint | Callable[..., object]

# Declared extension points and their entry point groups, filled by extension_point.
_POINTS: dict[object, str] = {}
# The implementation each point uses when none is named.
_DEFAULTS: dict[object, str] = {}


def extension_point(group: str, *, default: str | None = None) -> Callable[[T], T]:
    """Declare a contract as an extension point discovered from an entry point group.

    The contract is a class or a function stub; its call signature types the
    implementations registered for it. It is returned unchanged. ``default``
    names the implementation that ``Extensions.get`` returns when no name is
    given.

    Implementations install under the entry point ``group`` and are found by
    the entry point name, which a URL scheme or parameter gives::

        [project.entry-points."apache_dubbo.loadbalance"]
        p2c = "my_package.balance:P2CLoadBalance"

    `Extensions.register` adds one at runtime instead, as tests do.

    Use a function stub when the contract is one stateless operation whose
    result depends only on its arguments. Use a class when implementations hold
    state, own a lifecycle, or provide several methods. When unsure, use a
    class. Either way, the contract's docstring states what implementations
    must provide.
    """

    def declare(point: T) -> T:
        _POINTS[point] = group
        if default is not None:
            _DEFAULTS[point] = default
        return point

    return declare


class Extensions:
    """The implementations of the declared extension points, by name.

    An implementation is any callable with its point's call signature: a class
    or factory for a class contract, a function for a function contract.

    Use the shared ``extensions`` instance; a separate instance isolates
    registrations, for example in tests. Installed entry points are discovered
    on first use and kept as a snapshot, and a plugin is imported only when its
    name is first requested. Names are unique per point across installed and
    registered implementations. Register during setup, before concurrent use.
    """

    def __init__(self) -> None:
        self._discover = cache(metadata.entry_points)
        # Per point: entry points not yet loaded, or callables, by name.
        self._points: dict[object, dict[str, _Entry]] = {}

    def register(self, point: Callable[P, T], name: str, implementation: Callable[P, T]) -> None:
        """Add an implementation without calling it.

        Raises:
            ExtensionError: The point is not declared or the name is taken,
                including by an installed entry point that is not loaded yet.
            TypeError: The implementation is not callable.
        """
        entries = self._entries(point)
        if name in entries:
            raise ExtensionError(f"duplicate extension {name!r} in group {_POINTS[point]!r}")
        if not callable(implementation):
            raise TypeError("extension implementation must be callable")

        entries[name] = implementation

    def get(self, point: Callable[P, T], name: str | None) -> Callable[P, T]:
        """Return the implementation named ``name``, importing its plugin if needed.

        ``None`` names the default that the point declares.

        Raises:
            ExtensionError: The point or the name is unknown, and the message
                names the installed ones; the name is ``None`` and the point
                declares no default; importing the plugin fails, with the
                original exception as the cause; or the imported object is
                not callable.
        """
        entries = self._entries(point)
        group = _POINTS[point]
        if name is None:
            name = _DEFAULTS.get(point)
            if name is None:
                raise ExtensionError(f"no extension named and no default in group {group!r}")

        try:
            entry = entries[name]
        except KeyError:
            installed = ", ".join(sorted(entries)) or "none"
            raise ExtensionError(f"unknown extension {name!r} in group {group!r}; installed: {installed}") from None

        if isinstance(entry, metadata.EntryPoint):
            try:
                loaded = entry.load()
            except Exception as error:
                raise ExtensionError(
                    f"cannot load extension {name!r} in group {group!r} from {entry.value!r}"
                ) from error
            if not callable(loaded):
                raise ExtensionError(f"extension {name!r} in group {group!r} must be callable: {entry.value!r}")

            entry = entries[name] = loaded

        # Entry points are dynamic; this cast does not validate their signatures.
        return cast(Callable[P, T], entry)

    def names(self, point: object) -> list[str]:
        """Return the names of the installed and registered implementations, sorted, without importing any.

        Raises:
            ExtensionError: The point is not declared.
        """
        return sorted(self._entries(point))

    def _entries(self, point: object) -> dict[str, _Entry]:
        """Return the name table of a point, building it on first use."""
        entries = self._points.get(point)
        if entries is not None:
            return entries

        try:
            group = _POINTS[point]
        except KeyError:
            raise ExtensionError(f"unknown extension point: {point!r}") from None

        entries = {}
        for entry in self._discover().select(group=group):
            if entry.name in entries:
                raise ExtensionError(f"duplicate extension {entry.name!r} in group {group!r}")
            entries[entry.name] = entry

        # setdefault keeps the first table if two callers race to build one.
        return self._points.setdefault(point, entries)


extensions = Extensions()
