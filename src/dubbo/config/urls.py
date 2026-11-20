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

"""The URLs that the configuration gives each service and reference: those served, called and registered with."""

import uuid
from collections.abc import Collection, Mapping
from typing import TypeVar

import attrs

from dubbo.constants import (
    DEFAULT_PROTOCOL_HOST,
    DEFAULT_SUBSCRIBE,
    SSL_ENABLED_KEY,
    SUBSCRIBE_KEY,
    TAG_KEY,
    TOKEN_KEY,
)
from dubbo.extension import ApplicationScope
from dubbo.rpc.definition import Service
from dubbo.url import (
    ADVERTISED_PORT,
    APPLICATION_SCOPE,
    CONFIG_CENTER_URL,
    METADATA_CONSUMER_URL,
    METADATA_REPORT_URL,
    PROVIDER_URL,
    SSL_CONTEXT,
    URL,
)
from dubbo.utils.converters import boolean

from .exceptions import ConfigError
from .fields import to_url_parameters
from .models import DubboConfig, ProtocolConfig, ReferenceConfig, ServiceConfig, TLSConfig

__all__ = [
    "direct_urls",
    "internal_service_urls",
    "reference_registries",
    "reference_url",
    "service_registries",
    "service_urls",
]

T = TypeVar("T")

# The settings of a method that only its providers read, which provider URLs carry to consumers.
_SERVICE_METHOD_FIELDS = ("weight", "deprecated", "executes", "tps", "tps_interval")


def service_urls(config: DubboConfig, service: Service, scope: ApplicationScope) -> list[URL]:
    """Return the URL ``service`` is served with on each of its protocols, in the application of ``scope``.

    The parameters hold its settings, such as ``service.filter``, the
    service's over the provider's, and those of ``tls``; the attributes hold
    the scope and the configuration center of the application, and the
    server context of ``tls``, if set. Protocols that neither selects are
    all those defined. A ``token`` of true becomes one random token, which
    each protocol shares, and one of false none.

    Raises:
        ConfigError: The configuration of the service names a method it does not have.
    """
    interface = service.interface
    provider = config.provider
    configured = provider.services.get(interface) or ServiceConfig()
    _check_methods(f"service {interface!r}", configured.methods, service)

    token = uuid.uuid4().hex
    urls = []
    for name in _service_protocols(config, interface):
        protocol = config.protocols[name]
        parameters = _tls_parameters(config.tls) | to_url_parameters(
            config.shutdown, protocol, config.application, provider, configured
        )
        urls.append(
            URL(
                protocol=protocol.name or name,
                host=protocol.host or DEFAULT_PROTOCOL_HOST,
                port=protocol.port,
                path=interface,
                parameters=_with_token(parameters, token),
                attributes=_attributes(config, scope, config.tls and config.tls.server_context)
                | _advertised_port(config, protocol),
            )
        )

    return urls


def internal_service_urls(config: DubboConfig, interfaces: Collection[str], scope: ApplicationScope) -> dict[str, URL]:
    """Return the URL a service of the framework itself, such as the MetadataService, is served with on each protocol.

    The protocols are those that serve ``interfaces``, keyed by name; of
    several of one name, the first is taken. The parameters hold the
    settings of the protocol, of ``application``, ``shutdown`` and ``tls``,
    so that the service shares the server of ``interfaces``, but none of the
    provider or of a service; the attributes hold the scope and the server
    context of ``tls``, if set. The URLs have no path.
    """
    urls: dict[str, URL] = {}
    names = dict.fromkeys(name for interface in interfaces for name in _service_protocols(config, interface))
    for name in names:
        protocol = config.protocols[name]
        protocol_name = protocol.name or name
        if protocol_name in urls:
            continue
        urls[protocol_name] = URL(
            protocol=protocol_name,
            host=protocol.host or DEFAULT_PROTOCOL_HOST,
            port=protocol.port,
            parameters=_tls_parameters(config.tls) | to_url_parameters(config.shutdown, protocol, config.application),
            attributes={APPLICATION_SCOPE: scope}
            | _ssl_context(config.tls and config.tls.server_context)
            | _advertised_port(config, protocol),
        )

    return urls


def service_registries(config: DubboConfig, interface: str, scope: ApplicationScope) -> list[URL]:
    """Return the URL of each registry the service ``interface`` is registered with, in the application of ``scope``.

    Registries that neither the service nor the provider selects are all
    those defined; registration skips those that set ``register`` to false.
    """
    provider = config.provider
    service = provider.services.get(interface) or ServiceConfig()

    names = _first(service.registries, provider.registries, tuple(config.registries))
    return [_registry(config, name, scope) for name in names]


def reference_url(config: DubboConfig, service: Service, scope: ApplicationScope, *, generic: bool = False) -> URL:
    """Return the URL of the reference to ``service`` in the application of ``scope``.

    It is ``consumer://{advertised_host}/{interface}``, its host ``None``
    unless ``application.advertised_host`` is set. The parameters hold the
    settings of the reference, such as ``cluster``, and of its calls, which
    provider URLs take; the reference's come over the consumer's, field by
    field within ``triple``, and those of ``tls``, but not the settings of
    methods that only providers read, such as ``weight``, which would
    replace those of providers. The attributes hold the scope and the
    configuration center of the application, and the client context of
    ``tls``, if set.

    A ``generic`` reference calls methods by name, beyond those of
    ``service``, so its configuration may name any method.

    Raises:
        ConfigError: The configuration of the reference names a method the
            service does not have, and the reference is not generic.
    """
    interface = service.interface
    consumer = config.consumer
    reference = consumer.references.get(interface) or ReferenceConfig()
    if not generic:
        _check_methods(f"reference {interface!r}", reference.methods, service)

    methods = {
        name: attrs.evolve(method, **dict.fromkeys(_SERVICE_METHOD_FIELDS))
        for name, method in reference.methods.items()
    }
    parameters = _tls_parameters(config.tls) | to_url_parameters(
        config.shutdown, config.application, consumer, attrs.evolve(reference, methods=methods)
    )
    return URL(
        protocol="consumer",
        host=config.application.advertised_host,
        path=interface,
        parameters=parameters,
        attributes=_attributes(config, scope, config.tls and config.tls.client_context),
    )


def direct_urls(config: DubboConfig, reference: URL) -> list[URL]:
    """Return the URLs of the providers that the reference ``reference`` calls directly, if it names any in ``urls``.

    Each takes the parameters of ``reference`` over its own, but for the tag,
    which stays as written; its attributes; and the name of the service as
    its path when it has none. The attribute ``PROVIDER_URL`` keeps it as
    written, with that path.
    """
    interface = reference.path
    texts = (config.consumer.references.get(interface) or ReferenceConfig()).urls or ()
    parameters = {key: value for key, value in reference.parameters.items() if key != TAG_KEY}

    urls = []
    for text in texts:
        url = URL.parse(text)
        url = url.replace(path=url.path or interface)
        urls.append(url.replace(attributes={**reference.attributes, PROVIDER_URL: url}).update_parameters(parameters))
    return urls


def reference_registries(config: DubboConfig, interface: str, scope: ApplicationScope) -> list[URL]:
    """Return the URL of each registry the reference ``interface`` discovers providers in, in the application of ``scope``.

    A reference that sets ``urls`` discovers only in the registries it
    selects itself, if any. Registries that neither the reference nor the
    consumer selects are all those defined, less those that set
    ``subscribe`` to false.

    Raises:
        ConfigError: A reference without ``urls`` selects no registry, or
            none of those selected subscribes.
    """
    consumer = config.consumer
    reference = consumer.references.get(interface) or ReferenceConfig()
    owner = f"reference {interface!r}"

    if reference.urls:
        names = reference.registries or ()
    else:
        names = _first(reference.registries, consumer.registries, tuple(config.registries))
        if not names:
            raise ConfigError(f"{owner} needs urls, as in [tri://127.0.0.1:50051], or a registry")
    registries = [_registry(config, name, scope) for name in names]
    subscribed = [url for url in registries if url.get_parameter(SUBSCRIBE_KEY, boolean, DEFAULT_SUBSCRIBE)]
    if registries and not subscribed:
        raise ConfigError(f"{owner} subscribes to none of its registries, which all set subscribe to false")

    return subscribed


def _with_token(parameters: dict[str, str], generated: str) -> dict[str, str]:
    """Return ``parameters`` with a ``token`` of true replaced by ``generated``, and one of false left out."""
    match parameters.get(TOKEN_KEY):
        case "true":
            return parameters | {TOKEN_KEY: generated}
        case "false":
            return {key: value for key, value in parameters.items() if key != TOKEN_KEY}
        case _:
            return parameters


def _service_protocols(config: DubboConfig, interface: str) -> tuple[str, ...]:
    """Return the names of the protocols the service ``interface`` is served with."""
    provider = config.provider
    configured = provider.services.get(interface) or ServiceConfig()
    return _first(configured.protocols, provider.protocols, tuple(config.protocols))


def _registry(config: DubboConfig, name: str, scope: ApplicationScope) -> URL:
    # The MetadataService of instances is called with the TLS settings of the application.
    consumer = URL(
        protocol="consumer",
        parameters=_tls_parameters(config.tls),
        attributes={APPLICATION_SCOPE: scope} | _ssl_context(config.tls and config.tls.client_context),
    )
    attributes: dict[str, object] = {APPLICATION_SCOPE: scope, METADATA_CONSUMER_URL: consumer}
    if config.metadata_report is not None:
        attributes[METADATA_REPORT_URL] = config.metadata_report.to_url().replace(attributes={APPLICATION_SCOPE: scope})

    return config.registries[name].to_url().replace(attributes=attributes)


def _attributes(config: DubboConfig, scope: ApplicationScope, ssl_context: object) -> dict[str, object]:
    attributes: dict[str, object] = {APPLICATION_SCOPE: scope}
    if config.config_center is not None:
        attributes[CONFIG_CENTER_URL] = config.config_center.to_url().replace(attributes={APPLICATION_SCOPE: scope})

    return attributes | _ssl_context(ssl_context)


def _advertised_port(config: DubboConfig, protocol: ProtocolConfig) -> dict[str, object]:
    port = protocol.advertised_port or config.application.advertised_port
    return {} if port is None else {ADVERTISED_PORT: port}


def _tls_parameters(tls: TLSConfig | None) -> dict[str, str]:
    return {} if tls is None else {SSL_ENABLED_KEY: "true"} | to_url_parameters(tls)


def _ssl_context(context: object) -> dict[str, object]:
    return {} if context is None else {SSL_CONTEXT: context}


def _check_methods(owner: str, configured: Mapping[str, object], service: Service) -> None:
    unknown = sorted(set(configured) - {method.name for method in service.methods})
    if unknown:
        raise ConfigError(f"{owner} configures methods it does not have: {', '.join(unknown)}")


def _first(*values: tuple[T, ...] | None) -> tuple[T, ...]:
    """Return the first of ``values`` that is not ``None``, else an empty tuple."""
    return next((value for value in values if value is not None), ())
