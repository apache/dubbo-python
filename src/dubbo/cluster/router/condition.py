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
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from typing import Self, cast

import attrs

from dubbo.constants import APPLICATION_KEY
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import CONFIG_CENTER_URL, URL
from dubbo.utils.converters import to_text

from ..rule import RuleWatch, entries, flag, glob, mapping, rule_key
from .base import Router, providers_by_application, published

__all__ = ["ConditionRouter"]

_SUFFIX = ".condition-router"

_CLAUSE = re.compile(r"\s*([^\s=!&]+)\s*(!=|=)\s*(.*?)\s*")
_ARGUMENT = re.compile(r"arguments\[([0-9]+)\]")
_ATTACHMENT = re.compile(r"attachments\[(.+)\]")
_INTEGER = re.compile(r"[+-]?[0-9]+")

# Tests a value, given the URL of the reference that ``$key`` refers to.
_Pattern = Callable[[str, URL], bool]

# The most providers selected by destination kept, one for each destination and sequence of providers routed.
_SELECTIONS = 256


@attrs.define(frozen=True, kw_only=True)
class _Matcher:
    """A key whose value matches none of ``mismatches`` and, if there are any, one of ``matches``."""

    key: str
    matches: tuple[_Pattern, ...]
    mismatches: tuple[_Pattern, ...]

    def accepts(self, value: str | None, consumer: URL) -> bool:
        if value is None or any(pattern(value, consumer) for pattern in self.mismatches):
            return False
        return not self.matches or any(pattern(value, consumer) for pattern in self.matches)


@attrs.define(frozen=True, kw_only=True)
class _Destination:
    """The providers every one of ``then`` accepts, chosen in proportion to ``weight``."""

    then: tuple[_Matcher, ...]
    weight: int


@attrs.define(frozen=True, kw_only=True)
class _Condition:
    """The calls ``when`` accepts go to one of ``destinations``; with none, they are blocked."""

    when: tuple[_Matcher, ...]
    destinations: tuple[_Destination, ...]


@attrs.define(frozen=True, kw_only=True)
class _ConditionRule:
    force: bool
    conditions: tuple[_Condition, ...]


class ConditionRouter(Router):
    """Sends the calls each condition of a rule accepts to the providers it names.

    The rules are in the configuration center: ``{interface}:{version}:{group}.condition-router``
    for the service, then ``{provider application}.condition-router`` for
    the providers of each application but the consumer's, then
    ``{consumer application}.condition-router``, each applied to what those
    before it left. ``when`` and ``from`` match the URL of the reference and
    the call, by its ``method``, ``arguments[i]``, as text with ``None`` as
    ``null`` and booleans as ``true`` and ``false``, and ``attachments[key]``;
    ``then`` and ``to`` match the URLs of providers, where ``$key`` stands for
    that of the reference.

    The rules of the service and of the consumer application are read before
    entering ``async with`` returns; those of the provider applications once
    the providers name them. The providers each ``then`` and ``to`` selects
    are kept for the providers they were selected among, so that a call
    only tests ``when`` and ``from``, and a route stays the same sequence
    while the providers do not change.
    """

    def __init__(self, url: URL) -> None:
        center = cast(URL | None, url.attributes.get(CONFIG_CENTER_URL))
        self._url = url
        self._selections = _Selections(url)
        # The providers of each application among the last providers grouped.
        self._grouped: Sequence[Invoker] | None = None
        self._groups: dict[str | None, list[Invoker]] = {}
        self._application = url.parameters.get(APPLICATION_KEY)
        self._service = RuleWatch(center, _parse_rule)
        self._provider = RuleWatch(center, _parse_rule)
        self._consumer = RuleWatch(center, _parse_rule)
        self._stack = AsyncExitStack()

    def notify(self, invokers: Sequence[Invoker]) -> None:
        self._selections.clear()
        # Without providers, the rules of the last ones stay for the next.
        if invokers:
            applications = providers_by_application(invokers).keys() - {None, self._application}
            self._provider.follow_soon(*(f"{app}{_SUFFIX}" for app in applications))

    def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        invokers = self._route_by(self._service, invokers, invocation)
        if self._provider.rules and invokers:
            invokers = self._route_by_application(invokers, invocation)
        return self._route_by(self._consumer, invokers, invocation)

    async def aclose(self) -> None:
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            for rules in (self._service, self._provider, self._consumer):
                await stack.enter_async_context(rules)
            await self._service.follow(rule_key(self._url) + _SUFFIX)
            if self._application:
                await self._consumer.follow(self._application + _SUFFIX)
            self._stack = stack.pop_all()

        return self

    def _route_by(
        self, rules: RuleWatch[_ConditionRule], invokers: Sequence[Invoker], invocation: Invocation
    ) -> Sequence[Invoker]:
        for rule in rules.rules.values():
            if invokers:
                invokers = _route(rule, invokers, self._selections, invocation)
        return invokers

    def _route_by_application(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        """Route the providers of each application by the rule of that application."""
        if invokers is not self._grouped:
            self._grouped, self._groups = invokers, providers_by_application(invokers)

        parts = []
        for application, group in self._groups.items():
            rule = self._provider.rules.get(f"{application}{_SUFFIX}")
            parts.append(group if rule is None else _route(rule, group, self._selections, invocation))
        if all(part is group for part, group in zip(parts, self._groups.values(), strict=True)):
            return invokers
        return self._selections.join(parts)


def _parse_rule(data: Mapping[str, object]) -> _ConditionRule | None:
    """Return the condition rule ``data`` holds, or ``None`` if it is disabled or has no conditions.

    A condition is a ``when => then`` string, or a mapping of ``from`` and
    ``to``, a list of destinations chosen by weight.

    Raises:
        ValueError: ``data`` is not a condition rule.
    """
    if not flag(data, "enabled", True):
        return None

    conditions = tuple(
        _parse_expression(entry) if isinstance(entry, str) else _parse_destinations(entry)
        for entry in entries(data, "conditions")
    )
    if not conditions:
        return None
    return _ConditionRule(force=flag(data, "force", False), conditions=conditions)


def _parse_expression(text: str) -> _Condition:
    """Parse ``when => then``; without ``when`` or with ``true`` it accepts every call, and without ``then`` or with ``false`` it blocks them.

    Raises:
        ValueError: ``text`` is blank.
    """
    if not text.strip():
        raise ValueError("a condition must not be blank; write => to block every call")
    when, arrow, then = text.partition("=>")
    if not arrow:
        when, then = "", when
    when, then = when.strip(), then.strip()

    destinations = () if then in ("", "false") else (_Destination(then=_parse_side(then, then=True), weight=100),)
    return _Condition(when=_parse_when(when), destinations=destinations)


def _parse_destinations(value: object) -> _Condition:
    """Parse ``from`` and ``to``; without ``from`` it accepts every call, and a destination without ``match`` holds every provider."""
    entry = mapping(value, "a condition")
    destinations = []
    for item in entries(entry, "to"):
        target = mapping(item, "a destination")
        weight = int(str(target.get("weight", 100)))
        if weight <= 0:
            raise ValueError(f"the weight of a destination must be positive, not {weight}")
        then = str(target.get("match") or "").strip()
        destinations.append(_Destination(then=_parse_side(then, then=True) if then else (), weight=weight))

    source = mapping(entry.get("from") or {}, "from")
    return _Condition(when=_parse_when(str(source.get("match") or "").strip()), destinations=tuple(destinations))


def _parse_when(text: str) -> tuple[_Matcher, ...]:
    return () if text in ("", "true") else _parse_side(text, then=False)


def _parse_side(text: str, *, then: bool) -> tuple[_Matcher, ...]:
    """Parse clauses such as ``host = 10.0.0.* & zone != gray,blue``, where a key named twice gets the values of both.

    ``then`` tells the side that names providers, whose values may refer to the reference.
    """
    sides: dict[str, tuple[list[_Pattern], list[_Pattern]]] = {}
    for clause in text.split("&"):
        found = _CLAUSE.fullmatch(clause)
        values = found[3].split(",") if found else []
        if found is None or not all(value.strip() for value in values):
            raise ValueError(f"cannot read {clause.strip()!r} in the condition {text!r}")

        key = found[1].removeprefix("consumer.").removeprefix("provider.")
        matches, mismatches = sides.setdefault(key, ([], []))
        (mismatches if found[2] == "!=" else matches).extend(_compile(value.strip(), then=then) for value in values)

    return tuple(
        _Matcher(key=key, matches=tuple(matches), mismatches=tuple(mismatches))
        for key, (matches, mismatches) in sides.items()
    )


def _compile(pattern: str, *, then: bool) -> _Pattern:
    """Compile a range such as ``1~9`` or ``~9``, or a glob such as ``10.0.*``.

    On the side that names providers, ``$key`` is the glob that ``key`` of the reference holds.
    """
    if "~" in pattern:
        low, _, high = pattern.partition("~")
        if not (low or high):
            raise ValueError(f"the range {pattern!r} has no bound")
        start, end = int(low) if low else None, int(high) if high else None

        def in_range(value: str, consumer: URL) -> bool:
            if not _INTEGER.fullmatch(value):
                return False
            try:
                number = int(value)
            # Python refuses to convert more digits than sys.get_int_max_str_digits().
            except ValueError:
                return False
            return (start is None or start <= number) and (end is None or number <= end)

        return in_range

    if then and pattern.startswith("$"):
        key = pattern[1:]
        return lambda value, consumer: glob(_url_value(consumer, key), value)

    return lambda value, consumer: glob(pattern, value)


def _url_value(url: URL, key: str) -> str | None:
    """Return the ``host``, ``port``, ``protocol``, ``path`` or ``address`` of ``url``, else its parameter ``key``."""
    match key:
        case "host":
            return url.host
        case "port":
            return str(url.port) if url.port else None
        case "protocol":
            return url.protocol
        case "path":
            return url.path or None
        case "address":
            return url.address or None
        case _:
            return url.parameters.get(key)


class _Selections:
    """The providers each destination selects among a sequence of providers, so that a selection stays the same sequence.

    A selection is kept for the destination and the sequence it was made
    from, and a join of the selections of several applications for the
    sequences joined, until ``clear``.
    """

    def __init__(self, consumer: URL) -> None:
        # The URL of the reference, which ``$key`` refers to.
        self.consumer = consumer
        self._selected: dict[tuple[int, int], tuple[_Destination, Sequence[Invoker], Sequence[Invoker]]] = {}
        self._joined: dict[tuple[int, ...], tuple[tuple[Sequence[Invoker], ...], Sequence[Invoker]]] = {}

    def get(self, destination: _Destination, invokers: Sequence[Invoker]) -> Sequence[Invoker]:
        """Return those of ``invokers`` that every matcher of ``destination`` accepts, ``invokers`` itself if all."""
        key = id(destination), id(invokers)
        kept = self._selected.get(key)
        # The entry holds both, so neither id is reused while it is kept.
        if kept is not None:
            return kept[2]

        consumer = self.consumer
        selected = [
            invoker
            for invoker in invokers
            if all(
                matcher.accepts(_url_value(published(invoker), matcher.key), consumer) for matcher in destination.then
            )
        ]
        result = invokers if len(selected) == len(invokers) else selected
        if len(self._selected) >= _SELECTIONS:
            self._selected.clear()
        self._selected[key] = (destination, invokers, result)
        return result

    def join(self, parts: Sequence[Sequence[Invoker]]) -> Sequence[Invoker]:
        """Return the providers of ``parts`` in order, the same sequence for the same parts."""
        key = tuple(map(id, parts))
        kept = self._joined.get(key)
        # The entry holds the parts, so no id is reused while it is kept.
        if kept is not None:
            return kept[1]

        joined = [invoker for part in parts for invoker in part]
        if len(self._joined) >= _SELECTIONS:
            self._joined.clear()
        self._joined[key] = (tuple(parts), joined)
        return joined

    def clear(self) -> None:
        """Forget every selection and join."""
        self._selected.clear()
        self._joined.clear()


def _route(
    rule: _ConditionRule, invokers: Sequence[Invoker], selections: _Selections, invocation: Invocation
) -> Sequence[Invoker]:
    """Apply the conditions of ``rule`` in turn, each to the providers those before it left.

    A condition that leaves none keeps the providers, unless the rule is forced.
    """
    consumer = selections.consumer
    for condition in rule.conditions:
        if not invokers:
            break
        if not all(
            matcher.accepts(_call_value(matcher.key, consumer, invocation), consumer) for matcher in condition.when
        ):
            continue
        if not condition.destinations:
            return ()

        found = []
        for destination in condition.destinations:
            selected = selections.get(destination, invokers)
            if selected:
                found.append((selected, destination.weight))
        if found:
            invokers = random.choices([selected for selected, _ in found], [weight for _, weight in found])[0]
        elif rule.force:
            return ()
    return invokers


def _call_value(key: str, consumer: URL, invocation: Invocation) -> str | None:
    """Return the ``method``, ``arguments[i]`` or ``attachments[key]`` of ``invocation``, else what ``key`` names in ``consumer``."""
    if key in ("method", "methods"):
        return invocation.method
    if found := _ARGUMENT.fullmatch(key):
        index = int(found[1])
        if index >= len(invocation.arguments):
            return None
        return to_text(invocation.arguments[index])
    if found := _ATTACHMENT.fullmatch(key):
        value = invocation.attachments.get(found[1])
        return value if isinstance(value, str) else None
    return _url_value(consumer, key)
