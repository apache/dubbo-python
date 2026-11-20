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

"""Governance rules, such as routing and override rules, which the cluster follows in the configuration center."""

import logging
import re
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from typing import Generic, Self, TypeVar, cast

import anyio
import attrs
from anyio.abc import TaskGroup, TaskStatus

from dubbo.config.exceptions import ConfigError
from dubbo.config.parsers import get_parser
from dubbo.config_center import ConfigCenter, get_config_center
from dubbo.constants import GROUP_KEY, VERSION_KEY
from dubbo.extension import Resource
from dubbo.url import URL
from dubbo.utils import create_background_task_group, follow
from dubbo.utils.converters import is_true

__all__ = ["ParamMatch", "RuleWatch", "StringMatch", "entries", "flag", "glob", "mapping", "rule_key"]

_logger = logging.getLogger(__name__)

# The group of every governance rule in the configuration center.
_GROUP = "dubbo"
# The tests of a StringMatch, in the order it applies them.
_STRING_MATCHES = ("exact", "prefix", "regex", "wildcard", "empty", "noempty")

R = TypeVar("R")


class RuleWatch(Resource, Generic[R]):
    """The rules under a set of keys in the configuration center ``url`` names, read by ``parse``.

    Each rule is YAML; ``parse`` takes it as a mapping and returns ``None``
    for one that has no effect. ``rules`` holds the latest rule of each key
    followed that has one, none while ``url`` is ``None``, and ``changed`` is
    called after it changes. A rule that cannot be read is logged, and the
    one before stays.

    Entering ``async with`` connects, and closing stops following.
    """

    def __init__(
        self,
        url: URL | None,
        parse: Callable[[Mapping[str, object]], R | None],
        changed: Callable[[], None] = lambda: None,
    ) -> None:
        self.rules: dict[str, R] = {}
        self._url = url
        self._parse = parse
        self._changed = changed
        # The scope of the follower of each key followed.
        self._scopes: dict[str, anyio.CancelScope] = {}
        self._stack = AsyncExitStack()
        # Set once entered with a configuration center.
        self._center: ConfigCenter | None = None
        self._task_group: TaskGroup | None = None

    async def follow(self, *keys: str) -> None:
        """Follow the rules under ``keys`` instead, returning once each new one has been read, or failed to be, the first time.

        The keys still followed keep their rules.
        """
        if self._task_group is not None:
            for key in self._move(keys):
                await self._task_group.start(self._follow, key, self._scopes[key])

    def follow_soon(self, *keys: str) -> None:
        """Follow the rules under ``keys`` instead, reading each new one soon; the keys still followed keep their rules."""
        if self._task_group is not None:
            for key in self._move(keys):
                self._task_group.start_soon(self._follow, key, self._scopes[key])

    async def aclose(self) -> None:
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        if self._url is None:
            return self

        async with AsyncExitStack() as stack:
            self._center = await get_config_center(self._url)
            task_group = self._task_group = await stack.enter_async_context(create_background_task_group())
            stack.callback(task_group.cancel_scope.cancel)
            self._stack = stack.pop_all()

        return self

    def _move(self, keys: tuple[str, ...]) -> list[str]:
        """Stop following the keys not in ``keys``, and return those of ``keys`` to start following."""
        dropped = [key for key in self._scopes if key not in keys]
        for key in dropped:
            self._scopes.pop(key).cancel()
        added = [key for key in dict.fromkeys(keys) if key not in self._scopes]
        for key in added:
            self._scopes[key] = anyio.CancelScope()

        removed = [key for key in dropped if self.rules.pop(key, None) is not None]
        if removed:
            self._changed()
        return added

    async def _follow(
        self, key: str, scope: anyio.CancelScope, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED
    ) -> None:
        center = self._center
        assert center is not None

        async def receive(text: str | None) -> None:
            # A follower of a key no longer followed sets nothing.
            if self._scopes.get(key) is scope:
                self._receive(key, text)

        with scope:
            await follow(
                lambda: center.watch(key, group=_GROUP),
                receive,
                f"the rule {key}",
                retry_first=True,
                task_status=task_status,
            )

    def _receive(self, key: str, text: str | None) -> None:
        if text is None or not text.strip():
            self._set(key, None)
            return

        try:
            rule = self._parse(get_parser("yaml").loads(text))
        except (ConfigError, ValueError) as error:
            # Without the cause, whose message quotes the text, which may hold secrets.
            _logger.warning("Cannot read the rule %s; the one before stays: %s", key, error)
            return
        self._set(key, rule)

    def _set(self, key: str, rule: R | None) -> None:
        if rule is None:
            self.rules.pop(key, None)
        else:
            self.rules[key] = rule
        self._changed()


def rule_key(url: URL) -> str:
    """Return the key of the rules of the service ``url`` refers to: ``{interface}:{version}:{group}``, with the colons of empty parts kept."""
    parameters = url.parameters
    return f"{url.path}:{parameters.get(VERSION_KEY, '')}:{parameters.get(GROUP_KEY, '')}"


def flag(data: Mapping[str, object], key: str, default: bool) -> bool:
    """Return the boolean ``key`` of ``data``: true when it reads ``true`` in any case, ``default`` when absent."""
    value = data.get(key)
    return default if value is None else is_true(value)


def mapping(value: object, name: str) -> Mapping[str, object]:
    """Return ``value``, the mapping ``name`` of a rule.

    Raises:
        ValueError: ``value`` is not a mapping.
    """
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} of a rule must be a mapping")
    return cast(Mapping[str, object], value)


def entries(data: Mapping[str, object], key: str) -> list[object]:
    """Return the list ``key`` of ``data``, empty when absent.

    Raises:
        ValueError: The value is not a list.
    """
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} of a rule must be a list")
    return cast(list[object], value)


def glob(pattern: str | None, value: str) -> bool:
    """Match ``value`` with ``pattern``, in which the last ``*`` stands for any text and every other character for itself."""
    if pattern == "*":
        return True
    if not pattern or not value:
        return not pattern and not value

    prefix, star, suffix = pattern.rpartition("*")
    if not star:
        return value == pattern
    return value.startswith(prefix) and value.endswith(suffix)


@attrs.define(frozen=True, kw_only=True)
class StringMatch:
    """A test of a text in a rule, by the first of its fields that is set and applies."""

    exact: str | None = None
    prefix: str | None = None
    regex: re.Pattern[str] | None = None
    wildcard: str | None = None
    empty: str | None = None
    noempty: str | None = None

    @classmethod
    def from_rule(cls, value: object, name: str) -> Self:
        """Read the test ``name`` of a rule, a mapping of ``exact``, ``prefix``, ``regex``, ``wildcard``, ``empty`` or ``noempty``.

        Raises:
            ValueError: ``value`` is not a mapping, or its regex is invalid.
        """
        tests = mapping(value, name)
        fields = {field: str(tests[field]) for field in _STRING_MATCHES if tests.get(field) is not None}
        regex = None
        if "regex" in fields:
            try:
                regex = re.compile(fields.pop("regex"))
            except re.error as error:
                raise ValueError(f"{name} has an invalid regex") from error
        return cls(regex=regex, **fields)

    def matches(self, value: str | None) -> bool:
        if value is not None:
            if self.exact is not None:
                return value == self.exact
            if self.prefix is not None:
                return value.startswith(self.prefix)
            if self.regex is not None:
                return self.regex.fullmatch(value) is not None
            if self.wildcard is not None:
                return self.wildcard in ("*", value)
        if self.empty is not None:
            return not value
        return self.noempty is not None and bool(value)


@attrs.define(frozen=True, kw_only=True)
class ParamMatch:
    """A test of one URL parameter in a rule; one without a value matches nothing."""

    key: str
    value: StringMatch | None

    @classmethod
    def from_rule(cls, value: object) -> Self:
        """Read a mapping of ``key`` and ``value``, the test of the parameter.

        Raises:
            ValueError: ``value`` is not such a mapping.
        """
        entry = mapping(value, "a match")
        key = entry.get("key")
        if not isinstance(key, str):
            raise ValueError("a match of a parameter needs a key")

        test = entry.get("value")
        return cls(
            key=key, value=None if test is None else StringMatch.from_rule(test, f"the value of the match of {key}")
        )

    def matches(self, parameters: Mapping[str, str]) -> bool:
        return self.value is not None and self.value.matches(parameters.get(self.key))
