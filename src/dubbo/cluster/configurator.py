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

"""Override rules, which change the parameters of the URLs the consumers and the providers of a service use."""

import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from functools import partial
from typing import Literal, Self, cast

import attrs

from dubbo.constants import APPLICATION_KEY
from dubbo.extension import Resource
from dubbo.url import CONFIG_CENTER_URL, URL
from dubbo.utils.net import match_address, split_address

from .rule import ParamMatch, RuleWatch, StringMatch, entries, flag, glob, mapping, rule_key

__all__ = ["Overrides", "Side"]

_logger = logging.getLogger(__name__)

_SUFFIX = ".configurators"
# Addresses of a rule that stand for any host.
_ANY_HOSTS = frozenset({"0.0.0.0", "*"})

# The side of a service whose URLs the configs of a rule change.
Side = Literal["consumer", "provider"]


@attrs.define(frozen=True, kw_only=True)
class _AddressMatch:
    """A test of an address by the first of its fields that is set.

    ``cird`` is the address itself or an IP expression, as tag rules list
    providers; ``wildcard`` is ``*`` or ``0.0.0.0`` for any address, else a
    pattern with at most one ``*``; ``exact`` is the address itself.
    """

    cird: str | None = None
    wildcard: str | None = None
    exact: str | None = None

    @classmethod
    def from_rule(cls, value: object, name: str) -> Self:
        tests = mapping(value, name)
        return cls(
            **{field: str(tests[field]) for field in ("cird", "wildcard", "exact") if tests.get(field) is not None}
        )

    def matches(self, address: str | None) -> bool:
        if address is None:
            return False
        if self.cird is not None:
            if address == self.cird:
                return True
            host, port = split_address(address)
            try:
                return match_address(self.cird, host, int(port) if port else None)
            except ValueError:
                _logger.warning(
                    "Cannot match %s with the address %r of an override rule; it does not match",
                    address,
                    self.cird,
                    exc_info=True,
                )
                return False
        if self.wildcard is not None:
            return self.wildcard in _ANY_HOSTS or glob(self.wildcard, address)
        return address == self.exact


@attrs.define(frozen=True, kw_only=True)
class _Match:
    """The ``match`` of a config, which takes in what passes every test it sets."""

    # The host on the side of the config, and the provider.
    address: _AddressMatch | None
    provider_address: _AddressMatch | None
    # Each passes what one of its tests passes.
    services: tuple[StringMatch, ...] | None
    applications: tuple[StringMatch, ...] | None
    params: tuple[ParamMatch, ...]

    @classmethod
    def from_rule(cls, value: object) -> Self:
        """Read ``address``, ``providerAddress``, ``service``, ``app`` or ``application``, and ``param``."""
        entry = mapping(value, "a match")

        def address(name: str) -> _AddressMatch | None:
            return None if entry.get(name) is None else _AddressMatch.from_rule(entry[name], name)

        def oneof(name: str) -> tuple[StringMatch, ...] | None:
            if entry.get(name) is None:
                return None
            return tuple(StringMatch.from_rule(item, name) for item in entries(mapping(entry[name], name), "oneof"))

        return cls(
            address=address("address"),
            provider_address=address("providerAddress"),
            services=oneof("service"),
            applications=oneof("app" if entry.get("app") is not None else "application"),
            params=tuple(ParamMatch.from_rule(item) for item in entries(entry, "param")),
        )

    def matches(self, url: URL, host: str | None) -> bool:
        parameters = url.parameters
        application = parameters.get(APPLICATION_KEY)
        return (
            (self.address is None or self.address.matches(host))
            and (self.provider_address is None or self.provider_address.matches(url.address))
            and (self.services is None or any(test.matches(url.service_key) for test in self.services))
            and (self.applications is None or any(test.matches(application) for test in self.applications))
            and all(param.matches(parameters) for param in self.params)
        )


@attrs.define(frozen=True, kw_only=True)
class _Override:
    """Parameters for the URLs used at ``hosts`` of ``providers``, of ``services`` in ``applications``; an empty set matches any."""

    hosts: frozenset[str]
    # Each a host and a port, either None for any.
    providers: frozenset[tuple[str | None, int | None]]
    services: frozenset[str]
    applications: frozenset[str]
    match: _Match | None
    parameters: Mapping[str, str]

    def applies(self, url: URL, host: str | None) -> bool:
        """Return whether it applies to ``url``, a URL of a provider used at ``host``."""
        return (
            (not self.hosts or host in self.hosts)
            and (not self.providers or any(_at(provider, url) for provider in self.providers))
            and (not self.services or url.service_key in self.services)
            and (not self.applications or url.parameters.get(APPLICATION_KEY) in self.applications)
            and (self.match is None or self.match.matches(url, host))
        )


class Overrides(Resource):
    """The override rules of one side of a service, which change the parameters of the URLs of its providers that side uses.

    ``url`` is the URL of a reference for ``consumer``, which calls with the
    URLs of providers, and the URL a provider registers the service with for
    ``provider``. The rules are in the configuration center the attribute
    ``CONFIG_CENTER_URL`` of ``url`` names: ``{application}.configurators``, then
    ``{interface}:{version}:{group}.configurators``, whose parameters win.
    Their configs of ``side`` apply where their addresses and ``match`` take
    in the host of ``url``. ``changed`` is called after they change. Without
    a configuration center, they change nothing.

    The parameters take effect where the URLs are read: for consumers, those
    each provider is called with, such as ``timeout`` and ``weight``, and
    ``disabled`` or ``enabled``, but not those of the reference, such as
    ``cluster``, ``retries`` and ``loadbalance``; for providers, what they
    register, and so what consumers read from them, and the filters they
    serve through, but not the settings of their protocols.

    Entering ``async with`` reads them, and closing stops following them.
    """

    def __init__(self, url: URL, side: Side, changed: Callable[[], None] = lambda: None) -> None:
        application = url.parameters.get(APPLICATION_KEY)
        self._url = url
        # The keys of the rules, the one whose parameters win last.
        self._keys = [*([application + _SUFFIX] if application else []), rule_key(url) + _SUFFIX]
        center = cast(URL | None, url.attributes.get(CONFIG_CENTER_URL))
        self._rules = RuleWatch(center, partial(_parse_rule, side=side), changed)
        self._stack = AsyncExitStack()

    def configure(self, urls: Sequence[URL]) -> list[URL]:
        """Return ``urls``, URLs of providers, with the parameters of the overrides that apply to each."""
        rules = self._rules.rules
        overrides = [override for key in self._keys for override in rules.get(key, ())]
        if not overrides:
            return list(urls)

        host = self._url.host
        return [
            url.update_parameters(
                {
                    name: value
                    for override in overrides
                    if override.applies(url, host)
                    for name, value in override.parameters.items()
                }
            )
            for url in urls
        ]

    async def aclose(self) -> None:
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self._rules)
            await self._rules.follow(*self._keys)
            self._stack = stack.pop_all()

        return self


def _parse_rule(data: Mapping[str, object], side: Side) -> tuple[_Override, ...] | None:
    """Return the overrides of ``side`` that ``data`` holds, those for particular hosts last, or ``None`` for none.

    A rule of scope ``application`` has the application as ``key`` and may
    list ``services``; one of scope ``service`` has the service, as
    ``group/interface:version``, and may list ``applications``. Each of its
    ``configs`` gives ``parameters`` for ``side: consumer`` or ``provider``,
    the ``addresses`` of the hosts on that side, the ``providerAddresses`` of
    the providers, as ``host``, ``host:port``, ``[ipv6]:port`` or
    ``0.0.0.0:port``, and a ``match`` that the URLs must also pass.

    Raises:
        ValueError: ``data`` is not an override rule.
    """
    key = data.get("key")
    if not isinstance(key, str) or not key:
        raise ValueError("an override rule needs a key")

    by_application = data.get("scope") == "application"
    overrides = []
    for entry in entries(data, "configs"):
        config = mapping(entry, "a config")
        if config.get("side") != side or not flag(config, "enabled", True):
            continue

        parameters = {name: str(value) for name, value in mapping(config.get("parameters") or {}, "parameters").items()}
        if not parameters:
            raise ValueError("a config of an override rule needs parameters")
        listed = {
            name: frozenset(str(item) for item in entries(config, name)) - {"*"}
            for name in ("services", "applications")
        }
        hosts = frozenset(str(address) for address in entries(config, "addresses"))
        overrides.append(
            _Override(
                hosts=frozenset() if hosts & _ANY_HOSTS else hosts,
                providers=frozenset(_provider(str(address)) for address in entries(config, "providerAddresses")),
                services=listed["services"] if by_application else frozenset({key}),
                applications=frozenset({key}) if by_application else listed["applications"],
                match=None if config.get("match") is None else _Match.from_rule(config["match"]),
                parameters=parameters,
            )
        )

    if not overrides or not flag(data, "enabled", True):
        return None
    return tuple(sorted(overrides, key=lambda override: bool(override.hosts)))


def _provider(address: str) -> tuple[str | None, int | None]:
    host, port = split_address(address)
    return (None if host in _ANY_HOSTS else host), (None if port in (None, "*") else int(port))


def _at(provider: tuple[str | None, int | None], url: URL) -> bool:
    host, port = provider
    return host in (None, url.host) and port in (None, url.port)
