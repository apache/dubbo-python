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

import ipaddress
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Self, cast

import attrs

from dubbo.constants import FORCE_TAG_KEY, TAG_KEY
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import CONFIG_CENTER_URL, URL
from dubbo.utils.converters import boolean, is_true
from dubbo.utils.net import match_address, split_address

from ..rule import ParamMatch, RuleWatch, entries, flag, mapping
from .base import Router, providers_by_application, published

__all__ = ["TagRouter"]

_logger = logging.getLogger(__name__)

_SUFFIX = ".tag-router"

# A provider, as tag rules address it: its host and port.
_Endpoint = tuple[str | None, int | None]
_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# The most routes kept for one sequence of providers, one for each tag asked for and whether it is forced.
_ROUTES = 64


@attrs.define(frozen=True, kw_only=True)
class _Tag:
    """The providers of a tag: those at ``addresses``, else those every one of ``match`` accepts."""

    name: str
    addresses: tuple[str, ...]
    match: tuple[ParamMatch, ...] | None


@attrs.define(frozen=True, kw_only=True)
class _TagRule:
    force: bool
    tags: tuple[_Tag, ...]


class TagRouter(Router):
    """Sends a call to the providers of the tag it asks for, and a call that asks for none to the untagged.

    A call asks for the ``dubbo.tag`` attachment, else the ``dubbo.tag``
    parameter of the reference; ``*`` asks for every provider. A provider has
    the tag of the ``dubbo.tag`` parameter it publishes. With the
    configuration center, the rule ``{provider application}.tag-router`` of
    each application can tag its providers by address or by the parameters
    they publish instead; ``a|b|c`` then asks for the first of ``a|b|c``,
    ``a|b`` and ``a`` the rules name. When no provider has the tag, the call
    goes to the untagged, unless ``dubbo.force.tag`` of the call or the
    reference is ``true``, or a forced rule tags by address.

    The providers of each tag of the rules are found when the providers or
    the rules change, so a call looks them up. The route of each tag is
    kept for the providers it was found among, so that it stays the same
    sequence until they or the rules change.

    Raises:
        ValueError: ``dubbo.force.tag`` of the reference is not a boolean.
    """

    def __init__(self, url: URL) -> None:
        self._tag = url.parameters.get(TAG_KEY)
        self._force = url.get_parameter(FORCE_TAG_KEY, boolean, False)
        self._invokers: Sequence[Invoker] = ()
        # The providers of each tag of the rules, of any of them, and the tags of forced rules.
        self._tagged: dict[str, frozenset[_Endpoint]] = {}
        self._all_tagged: frozenset[_Endpoint] = frozenset()
        self._forced: frozenset[str] = frozenset()
        # The routes among the last providers routed, by the tag asked for and whether it is forced.
        self._routed: Sequence[Invoker] | None = None
        self._routes: dict[tuple[str | None, bool], Sequence[Invoker]] = {}
        self._rules = RuleWatch(cast(URL | None, url.attributes.get(CONFIG_CENTER_URL)), _parse_rule, self._resolve)

    def notify(self, invokers: Sequence[Invoker]) -> None:
        self._invokers = invokers
        # Without providers, the rules of the last ones stay for the next.
        if invokers:
            applications = providers_by_application(invokers).keys() - {None}
            self._rules.follow_soon(*(f"{app}{_SUFFIX}" for app in applications))
        self._resolve()

    def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        if not invokers:
            return invokers

        tag = _attachment(invocation, TAG_KEY) or self._tag
        if tag == "*":
            return invokers

        forced = _attachment(invocation, FORCE_TAG_KEY)
        force = is_true(forced) if forced else self._force
        if invokers is not self._routed:
            self._routed, self._routes = invokers, {}
        routed = self._routes.get((tag, force))
        if routed is None:
            if len(self._routes) >= _ROUTES:
                self._routes.clear()
            routed = self._routes[tag, force] = self._route(invokers, tag, force)
        return routed

    async def aclose(self) -> None:
        await self._rules.aclose()

    async def __aenter__(self) -> Self:
        await self._rules.__aenter__()
        return self

    def _route(self, invokers: Sequence[Invoker], tag: str | None, force: bool) -> Sequence[Invoker]:
        if not self._rules.rules:
            return self._route_by_parameter(invokers, tag, force)

        if tag:
            name = self._select(tag, force)
            if name is not None:
                tagged = self._tagged[name]
                result = _narrow(invokers, lambda invoker: _endpoint(invoker.url) in tagged)
                if result or name in self._forced:
                    return result
            else:
                result = _narrow(invokers, lambda invoker: _tag(invoker) == tag)
            if result or force:
                return result

        all_tagged = self._all_tagged
        return _narrow(invokers, lambda invoker: _endpoint(invoker.url) not in all_tagged and _untagged(invoker))

    def _route_by_parameter(self, invokers: Sequence[Invoker], tag: str | None, force: bool) -> Sequence[Invoker]:
        if not tag:
            return _narrow(invokers, _untagged)

        result = _narrow(invokers, lambda invoker: _tag(invoker) == tag)
        if not result and not force:
            return _narrow(invokers, _untagged)
        return result

    def _select(self, tag: str, force: bool) -> str | None:
        """Return ``tag``, or the first of its levels, that the rules name; ``None`` if they name none."""
        if force or "|" not in tag:
            return tag if tag in self._tagged else None

        levels = tag.split("|")
        for end in range(len(levels), 0, -1):
            name = "|".join(levels[:end])
            if name in self._tagged:
                return name
        return None

    def _resolve(self) -> None:
        tagged: dict[str, frozenset[_Endpoint]] = {}
        forced: set[str] = set()
        applications = providers_by_application(self._invokers)
        for key, rule in self._rules.rules.items():
            # The rule of an application tags its providers alone.
            own = applications.get(key.removesuffix(_SUFFIX), [])
            addresses = _Addresses(own)
            for tag in rule.tags:
                if tag.addresses:
                    found = addresses.listed(tag.addresses)
                else:
                    match = tag.match or ()
                    found = frozenset(
                        _endpoint(invoker.url)
                        for invoker in own
                        if all(test.matches(published(invoker).parameters) for test in match)
                    )
                    # A tag by parameters that no provider has is named by no rule.
                    if not found:
                        continue
                tagged[tag.name] = tagged.get(tag.name, frozenset()) | found
                if rule.force:
                    forced.add(tag.name)

        self._tagged = tagged
        self._all_tagged = frozenset().union(*tagged.values())
        self._forced = frozenset(forced)
        self._routed = None


def _parse_rule(data: Mapping[str, object]) -> _TagRule | None:
    """Return the tag rule ``data`` holds, or ``None`` if it is disabled or tags nothing.

    Raises:
        ValueError: ``data`` is not a tag rule.
    """
    tags = tuple(_parse_tag(entry) for entry in entries(data, "tags"))
    if not tags or not flag(data, "enabled", True):
        return None
    return _TagRule(force=flag(data, "force", False), tags=tags)


def _parse_tag(value: object) -> _Tag:
    entry = mapping(value, "a tag")
    name = entry.get("name")
    if not isinstance(name, str):
        raise ValueError("a tag of a tag rule needs a name")

    addresses = tuple(str(address).strip() for address in entries(entry, "addresses"))
    match = None
    if entry.get("match") is not None:
        match = tuple(ParamMatch.from_rule(item) for item in entries(entry, "match"))
    if not addresses and match is None:
        raise ValueError(f"tag {name} needs addresses or match")
    return _Tag(name=name, addresses=addresses, match=match)


def _attachment(invocation: Invocation, key: str) -> str | None:
    value = invocation.attachments.get(key)
    return value if isinstance(value, str) else None


def _narrow(invokers: Sequence[Invoker], keep: Callable[[Invoker], bool]) -> Sequence[Invoker]:
    kept = [invoker for invoker in invokers if keep(invoker)]
    return invokers if len(kept) == len(invokers) else kept


def _endpoint(url: URL) -> _Endpoint:
    return url.host, url.port


def _tag(invoker: Invoker) -> str | None:
    return published(invoker).parameters.get(TAG_KEY)


def _untagged(invoker: Invoker) -> bool:
    return not _tag(invoker)


class _Addresses:
    """The providers of one application, as tag rules list them by address.

    A pattern that names one address is looked up; any other is tested
    against each provider.
    """

    def __init__(self, invokers: Sequence[Invoker]) -> None:
        self._urls = [invoker.url for invoker in invokers]
        self._hosts: dict[_IPAddress, set[_Endpoint]] = {}
        self._endpoints: dict[tuple[_IPAddress, int], set[_Endpoint]] = {}
        # Those whose host is not an IP address, which every pattern is tested against.
        self._named: list[URL] = []
        for url in self._urls:
            try:
                address = ipaddress.ip_address(url.host)  # ty: ignore[invalid-argument-type]
            except ValueError:
                self._named.append(url)
                continue
            self._hosts.setdefault(address, set()).add(_endpoint(url))
            self._endpoints.setdefault((address, url.port or 0), set()).add(_endpoint(url))

    def listed(self, patterns: Sequence[str]) -> frozenset[_Endpoint]:
        """Return the providers one of ``patterns`` lists."""
        found: set[_Endpoint] = set()
        for pattern in patterns:
            exact = _exact(pattern)
            if exact is None:
                found.update(_endpoint(url) for url in self._urls if _listed(pattern, url))
                continue

            address, port = exact
            found |= self._hosts.get(address, set()) if port is None else self._endpoints.get((address, port), set())
            found.update(_endpoint(url) for url in self._named if _listed(pattern, url))
        return frozenset(found)


def _exact(pattern: str) -> tuple[_IPAddress, int | None] | None:
    """Return the IP address and the port, if any, of ``pattern`` when it names one address; else ``None``."""
    host, port = split_address(pattern)
    if port is not None and not (port.isdecimal() and str(int(port)) == port):
        return None
    try:
        return ipaddress.ip_address(host), None if port is None else int(port)
    except ValueError:
        return None


def _listed(pattern: str, url: URL) -> bool:
    try:
        return match_address(pattern, url.host, url.port)
    except ValueError:
        _logger.warning(
            "Cannot match the provider %s with the address %r of a tag rule; it is not listed",
            url,
            pattern,
            exc_info=True,
        )
        return False
