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

import re
from collections.abc import Callable, Mapping
from typing import Any, Self, TypeVar, cast
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

import attrs

from dubbo.constants import ACCESS_KEY_KEY, GROUP_KEY, SECRET_KEY_KEY, TOKEN_KEY, VERSION_KEY
from dubbo.extension import ApplicationScope
from dubbo.utils import freeze_mapping
from dubbo.utils.net import format_address

__all__ = [
    "ADVERTISED_PORT",
    "APPLICATION_SCOPE",
    "CONFIG_CENTER_URL",
    "METADATA_CONSUMER_URL",
    "METADATA_REPORT_URL",
    "PROVIDER_URL",
    "SSL_CONTEXT",
    "URL",
    "service_key",
]

T = TypeVar("T")
D = TypeVar("D")

# The keys of URL.attributes the framework sets: "dubbo." and the name of the constant in lowercase, ending with
# _url for one that holds a URL. An extension names its own keys after its package.
# On the URL a service is served with: the port registries publish in place of the one bound, if the configuration
# sets one.
ADVERTISED_PORT = "dubbo.advertised_port"
# The attribute that holds the scope of the application that made a URL.
APPLICATION_SCOPE = "dubbo.application_scope"
# The attribute that holds the URL of the configuration center of the application that made a URL, if it has one.
CONFIG_CENTER_URL = "dubbo.config_center_url"
# On a registry URL: the URL whose settings, such as TLS, the calls to the MetadataService of the instances it finds
# use.
METADATA_CONSUMER_URL = "dubbo.metadata_consumer_url"
# The attribute that holds the URL of the metadata report a registry URL stores metadata in, if not the registry itself.
METADATA_REPORT_URL = "dubbo.metadata_report_url"
# On the URL a consumer calls a provider with: the URL the provider published, before the settings of the reference
# and the override rules changed it.
PROVIDER_URL = "dubbo.provider_url"
# The attribute that holds the ssl.SSLContext the application gives the server or client of a URL, if it gives one.
SSL_CONTEXT = "dubbo.ssl_context"

_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")
# The parameters whose values are credentials; ``str`` and ``repr`` hide them.
_SECRET_PARAMETERS = frozenset({ACCESS_KEY_KEY, SECRET_KEY_KEY, TOKEN_KEY})


def _decode(value: str | None) -> str | None:
    # urlsplit leaves percent-escapes in place; components hold decoded text.
    return None if value is None else unquote(value, errors="strict")


def _host(value: str | None) -> str | None:
    # Host names are case-insensitive; an empty host is no host.
    return value.lower() or None if value is not None else None


def _hide_secrets(parameters: Mapping[str, str]) -> dict[str, str]:
    return {key: "***" if key in _SECRET_PARAMETERS else value for key, value in parameters.items()}


def _repr_parameters(parameters: Any) -> str:
    return repr(_hide_secrets(parameters))


def _check_port(_url: object, _attribute: object, port: int | None) -> None:
    if port is not None and not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")


@attrs.define(frozen=True, kw_only=True)
class URL:
    """An immutable Dubbo URL: what an extension is selected and configured by.

    Every component but the host holds decoded text, which
    ``render_as_string`` escapes; the host is kept as written, in lowercase.

    Attributes:
        protocol: Scheme that selects the implementation, in lowercase.
        host: Host name in lowercase, or an IPv6 address without brackets.
        port: Port from 0 to 65535, if any.
        path: Path without its leading slash, such as a service name.
        username: User name, if any.
        password: Password, if any; ``repr`` and ``str`` hide it.
        parameters: Read-only query parameters. A repeated key keeps its last
            value, and equality ignores the order. ``repr`` and ``str`` hide
            the values of ``token``, ``accessKey`` and ``secretKey``.
        attributes: Values that text cannot hold, such as the scope of the
            application that made the URL under `APPLICATION_SCOPE`. They are
            read-only, set when the URL is made or with `replace`, and not
            part of the text, equality or ``repr``: URLs that differ only in
            attributes share one extension instance in `ApplicationScope.share`.

    Raises:
        ValueError: The protocol is not a scheme, the port is out of range, a
            password has no username, or a port or username has no host.
    """

    protocol: str = attrs.field(converter=str.lower)
    host: str | None = attrs.field(default=None, converter=_host)
    port: int | None = attrs.field(default=None, validator=_check_port)
    path: str = ""
    username: str | None = None
    password: str | None = attrs.field(default=None, repr=False)
    # Left out of the hash, which a read-only mapping cannot take part in; equality still compares it.
    parameters: Mapping[str, str] = attrs.field(
        factory=dict, converter=freeze_mapping, hash=False, repr=_repr_parameters
    )
    attributes: Mapping[str, object] = attrs.field(factory=dict, converter=freeze_mapping, eq=False, repr=False)

    def __attrs_post_init__(self) -> None:
        if not _SCHEME.match(self.protocol):
            raise ValueError(f"protocol must be a URL scheme, not {self.protocol!r}")
        if self.password is not None and self.username is None:
            raise ValueError("password requires username")
        if self.host is None and (self.port is not None or self.username is not None):
            raise ValueError("port and username require host")

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse a URL such as ``zookeeper://user:secret@127.0.0.1:2181/path?timeout=3000``.

        Surrounding whitespace is ignored. Components are decoded once, and the
        query is form-encoded: ``+`` means a space and a bare key has an empty
        value.

        Raises:
            ValueError: The text has no scheme, an invalid host or port,
                escapes that do not decode to UTF-8, or a fragment.
        """
        try:
            parts = urlsplit(text.strip())
            port = parts.port
        except ValueError:
            # The errors of urlsplit quote the authority, which may hold a password.
            raise ValueError("URL has an invalid host or port") from None
        if not parts.scheme:
            raise ValueError("URL needs a scheme, as in zookeeper://127.0.0.1:2181")
        if parts.fragment:
            raise ValueError("URL fragments are not supported")

        return cls(
            protocol=parts.scheme,
            host=parts.hostname,
            port=port,
            path=unquote(parts.path, errors="strict").removeprefix("/"),
            username=_decode(parts.username),
            password=_decode(parts.password),
            parameters=dict(parse_qsl(parts.query, keep_blank_values=True, errors="strict")),
        )

    @property
    def address(self) -> str:
        """The host and the port, if any, as in ``127.0.0.1:2181``, an IPv6 host in brackets; empty without a host."""
        return format_address(self.host or "", self.port)

    @property
    def userinfo(self) -> str | None:
        """The user and the password, if any, unescaped, as in ``user:secret``; ``None`` without a user."""
        if self.username is None:
            return None
        return self.username if self.password is None else f"{self.username}:{self.password}"

    @property
    def scope(self) -> ApplicationScope:
        """The `ApplicationScope` of the application that made the URL, under `APPLICATION_SCOPE`; extensions share clients and state through it.

        Raises:
            RuntimeError: No application made the URL, as for one from `parse`.
        """
        scope = self.attributes.get(APPLICATION_SCOPE)
        if scope is None:
            raise RuntimeError(f"{self} belongs to no application")
        return cast(ApplicationScope, scope)

    @property
    def service_key(self) -> str:
        """``group/path:version`` from the path and the ``group`` and ``version`` parameters, as `service_key` makes it."""
        return service_key(self.path, self.parameters.get(GROUP_KEY), self.parameters.get(VERSION_KEY))

    def get_parameter(self, key: str, convert: Callable[[str], T], default: D) -> T | D:
        """Return the parameter ``key`` converted by ``convert``, or ``default`` when it is absent.

        ``convert`` takes the text and raises `ValueError` to reject it, as
        `int`, `float` and the converters in `dubbo.utils.converters` do, as in
        ``url.get_parameter("timeout", milliseconds, 3.0)``.

        Raises:
            ValueError: ``convert`` rejects the text; the message names the key.
        """
        value = self.parameters.get(key)
        if value is None:
            return default

        return _convert(key, value, convert)

    def get_method_parameters(self, key: str, convert: Callable[[str], T]) -> dict[str, T]:
        """Return the parameter ``key`` of each method that sets it as ``{method}.{key}``, by method, converted by ``convert``.

        For ``a.timeout=1&b.timeout=2&timeout=3``,
        ``get_method_parameters("timeout", int)`` is ``{"a": 1, "b": 2}``;
        ``timeout`` belongs to no method.

        Raises:
            ValueError: ``convert`` rejects the text; the message names the key.
        """
        suffix = f".{key}"
        return {
            name.removesuffix(suffix): _convert(name, value, convert)
            for name, value in self.parameters.items()
            if name.endswith(suffix) and name != suffix
        }

    def replace(self, **changes: Any) -> Self:
        """Return a copy with the components ``changes`` names replaced, as in ``url.replace(port=50051)``.

        Raises:
            ValueError: As the constructor raises.
            TypeError: ``changes`` names a component the URL does not have.
        """
        return attrs.evolve(self, **changes)

    def update_parameters(self, parameters: Mapping[str, str]) -> Self:
        """Return a copy with ``parameters`` added, replacing the values of existing keys."""
        return self.replace(parameters={**self.parameters, **parameters})

    def render_as_string(self, *, hide_secrets: bool = True) -> str:
        """Render the URL, escaping each component.

        The secrets, the password and the values of the parameters
        ``token``, ``accessKey`` and ``secretKey``, render as ``***`` unless
        ``hide_secrets`` is false, so that logs and error messages never
        reveal them.
        """
        authority = self.address
        if self.username is not None:
            userinfo = quote(self.username, safe="")
            if self.password is not None:
                userinfo += ":" + ("***" if hide_secrets else quote(self.password, safe=""))
            authority = f"{userinfo}@{authority}"

        path = "/" + quote(self.path) if self.path else ""
        parameters = _hide_secrets(self.parameters) if hide_secrets else self.parameters
        query = "?" + urlencode(list(parameters.items())) if parameters else ""
        return f"{self.protocol}://{authority}{path}{query}"

    def __str__(self) -> str:
        """Render the URL with the password and the secret parameters hidden."""
        return self.render_as_string()


def service_key(interface: str, group: str | None, version: str | None) -> str:
    """Return the key that registries and servers tell services apart by: ``group/interface:version``, leaving out an empty group or version, as in ``a/com.example.UserService:1.0``."""
    key = f"{group}/{interface}" if group else interface

    return f"{key}:{version}" if version else key


def _convert(key: str, value: str, convert: Callable[[str], T]) -> T:
    try:
        return convert(value)
    except ValueError as error:
        raise ValueError(f"URL parameter {key!r}: {error}") from None
