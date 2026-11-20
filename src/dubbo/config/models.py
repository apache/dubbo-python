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

import enum
import os
import re
import ssl
from collections.abc import Mapping
from typing import Self

import attrs
from attrs import converters, validators

from dubbo.constants import (
    ACCESSLOG_KEY,
    ACTIVES_KEY,
    APPLICATION_KEY,
    ARCHITECTURE_KEY,
    BACKUP_KEY,
    CA_CERT_FILE_KEY,
    CHECK_KEY,
    CLUSTER_KEY,
    COMPRESSOR_KEY,
    CONNECT_TIMEOUT_KEY,
    CONNECTION_INITIAL_WINDOW_SIZE_KEY,
    DEFAULT_CONFIG_CENTER_TIMEOUT,
    DEFAULT_PROTOCOL,
    DEPRECATED_KEY,
    ENVIRONMENT_KEY,
    EXECUTES_KEY,
    GROUP_KEY,
    HEALTH_ENABLED_KEY,
    HEARTBEAT_KEY,
    HEARTBEAT_TIMEOUT_KEY,
    INITIAL_WINDOW_SIZE_KEY,
    KEEP_ALIVE_INTERVAL_KEY,
    KEEP_ALIVE_TIMEOUT_KEY,
    LOADBALANCE_KEY,
    MAX_CONCURRENT_CALLS_KEY,
    MAX_CONCURRENT_STREAMS_KEY,
    MAX_HEADER_LIST_SIZE_KEY,
    MAX_RECEIVE_MESSAGE_SIZE_KEY,
    NAMESPACE_KEY,
    ORGANIZATION_KEY,
    OWNER_KEY,
    PAYLOAD_KEY,
    PREFERRED_KEY,
    PROVIDED_BY_KEY,
    REFERENCE_FILTER_KEY,
    REFLECTION_ENABLED_KEY,
    REGISTER_KEY,
    REGISTER_MODE_KEY,
    RETRIES_KEY,
    ROUTER_KEY,
    SERIALIZATION_KEY,
    SERVICE_FILTER_KEY,
    SHUTWAIT_KEY,
    STICKY_KEY,
    SUBSCRIBE_KEY,
    TAG_KEY,
    TIMEOUT_KEY,
    TLS_CERT_FILE_KEY,
    TLS_KEY_FILE_KEY,
    TLS_SERVER_NAME_KEY,
    TOKEN_KEY,
    TPS_INTERVAL_KEY,
    TPS_KEY,
    TRIPLE_KEY,
    VERSION_KEY,
    WARMUP_KEY,
    WEIGHT_KEY,
    ZONE_KEY,
)
from dubbo.filter.base import ATTEMPT_FILTER_KEY
from dubbo.url import URL
from dubbo.utils.converters import milliseconds, to_milliseconds

from .fields import check_address_keys, check_url_keys, env_variable, to_url_parameters, url_nested, url_parameter

__all__ = [
    "ApplicationConfig",
    "ConfigCenterConfig",
    "ConsumerConfig",
    "DubboConfig",
    "DubboProtocolConfig",
    "MetadataReportConfig",
    "MetadataType",
    "MethodConfig",
    "ProtocolConfig",
    "ProviderConfig",
    "ReferenceConfig",
    "RegistryConfig",
    "RegistryMode",
    "ServiceConfig",
    "ShutdownConfig",
    "TLSConfig",
    "TripleConfig",
]

_positive = validators.optional(validators.gt(0))
_non_negative = validators.optional(validators.ge(0))
_names = validators.optional(validators.deep_iterable(validators.instance_of(str), validators.instance_of(tuple)))
_parameters = validators.deep_mapping(validators.instance_of(str), validators.instance_of(str))


# Scheme, authority, then the path and query, of an address with comma-separated hosts.
_ADDRESS = re.compile(r"(?P<scheme>[^:/?]+)://(?P<authority>[^/?]*)(?P<rest>.*)", re.DOTALL)


def _address_url(address: str) -> URL:
    """Return the URL of an address, the hosts after the first moved to ``backup``.

    Raises:
        ValueError: The address has no scheme or host, an empty host, or
            lists further hosts both after commas and in ``backup``.
    """
    match = _ADDRESS.fullmatch(address.strip())
    if match is None:
        raise ValueError("needs a scheme, as in zookeeper://127.0.0.1:2181")

    userinfo, at, hosts = match["authority"].rpartition("@")
    host, *backups = hosts.split(",")
    if not all(backups):
        raise ValueError("lists an empty host")

    url = URL.parse(f"{match['scheme']}://{userinfo}{at}{host}{match['rest']}")
    if url.host is None:
        raise ValueError("needs a host, as in zookeeper://127.0.0.1:2181")
    if not backups:
        return url

    if BACKUP_KEY in url.parameters:
        raise ValueError(f"lists further hosts both after commas and in {BACKUP_KEY!r}")
    return url.update_parameters({BACKUP_KEY: ",".join(backups)})


def _address(_: object, attribute: "attrs.Attribute[str]", value: str) -> None:
    try:
        _address_url(value)
    except ValueError as error:
        raise ValueError(f"{attribute.name} {error}") from None


def _url(_: object, attribute: "attrs.Attribute[str]", value: str) -> None:
    try:
        url = URL.parse(value)
    except ValueError as error:
        raise ValueError(f"{attribute.name} {error}") from None
    if url.host is None:
        raise ValueError(f"{attribute.name} needs a host, as in tri://127.0.0.1:50051")


def _token(_: object, attribute: "attrs.Attribute[bool | str | None]", value: bool | str | None) -> None:
    if value == "":
        raise ValueError(f"{attribute.name} must not be empty; set it to false to require none")


_urls = validators.optional(
    validators.deep_iterable(validators.and_(validators.instance_of(str), _url), validators.instance_of(tuple))
)

# The URL parameters that the fields of services, references and methods become.
_GROUP = url_parameter(GROUP_KEY)
_VERSION = url_parameter(VERSION_KEY)
_TIMEOUT = url_parameter(TIMEOUT_KEY, to_milliseconds)
_RETRIES = url_parameter(RETRIES_KEY)
_WEIGHT = url_parameter(WEIGHT_KEY)
_WARMUP = url_parameter(WARMUP_KEY, to_milliseconds)
_TAG = url_parameter(TAG_KEY)
_CLUSTER = url_parameter(CLUSTER_KEY)
_LOADBALANCE = url_parameter(LOADBALANCE_KEY)
_STICKY = url_parameter(STICKY_KEY)
_CHECK = url_parameter(CHECK_KEY)
_SERVICE_FILTERS = url_parameter(SERVICE_FILTER_KEY, ",".join)
_REFERENCE_FILTERS = url_parameter(REFERENCE_FILTER_KEY, ",".join)
_ATTEMPT_FILTERS = url_parameter(ATTEMPT_FILTER_KEY, ",".join)
_ROUTERS = url_parameter(ROUTER_KEY, ",".join)
_TOKEN = url_parameter(TOKEN_KEY)
_ACCESSLOG = url_parameter(ACCESSLOG_KEY)
_EXECUTES = url_parameter(EXECUTES_KEY)
_TPS = url_parameter(TPS_KEY)
_TPS_INTERVAL = url_parameter(TPS_INTERVAL_KEY, to_milliseconds)
_DEPRECATED = url_parameter(DEPRECATED_KEY)
_ACTIVES = url_parameter(ACTIVES_KEY)
_SERIALIZATION = url_parameter(SERIALIZATION_KEY)


class RegistryMode(enum.StrEnum):
    """How an application registers its services and discovers providers in a registry.

    Attributes:
        INTERFACE: Providers register each service URL, and consumers
            discover them by interface.
        INSTANCE: Providers register one instance per application, which
            serves its metadata, and consumers discover the instances of the
            applications that provide an interface.
        ALL: Providers register both ways. Consumers call the providers
            found by instance while there are any, else those found by
            interface.
    """

    INTERFACE = "interface"
    INSTANCE = "instance"
    ALL = "all"


class MetadataType(enum.StrEnum):
    """Where consumers read the metadata of an application's instances.

    Attributes:
        LOCAL: Each instance serves its metadata itself, through
            MetadataServiceV2 over tri, else the MetadataService 1.0.0 over
            dubbo, which needs the hessian2 extra.
        REMOTE: The metadata is stored in `DubboConfig.metadata_report`, else
            in the registry.
    """

    LOCAL = "local"
    REMOTE = "remote"


# Classes run from leaves to the root: field annotations are evaluated when each
# class is created, and structure_config reads them as real types.
#
# Optional fields default to None, meaning "not set": a lower configuration
# layer or the enclosing section supplies the value. Effective defaults are
# applied where the configuration is used, so None never hides a lower layer.


@attrs.define(frozen=True, kw_only=True)
class ApplicationConfig:
    """Identify the application that provides or consumes services.

    Attributes:
        name: Application name, shown to registries and governance tools;
            required once a registry is defined, since registries group
            instances by it.
        version: Application version, if any.
        owner: People responsible for the application, separated by commas.
        organization: Organization that owns the application.
        architecture: Architecture of the application, as its owners
            describe it, such as a business domain.
        environment: Environment the application runs in, such as
            ``develop``, ``test`` or ``product``.
        metadata_type: Where consumers read the metadata of this
            application's instances; ``None`` means ``local``.
        advertised_host: Address that registries and the rules of others
            see for this application, when the address it listens on
            cannot be reached, as behind NAT or in a container; ``None``
            finds one. The ``DUBBO_IP_TO_REGISTRY`` environment variable
            sets it.
        advertised_port: Port registered in place of the one it listens on
            for each protocol whose ``advertised_port`` is not set; ``None``
            registers that one. The ``DUBBO_PORT_TO_REGISTRY`` environment
            variable sets it.
    """

    name: str | None = attrs.field(
        default=None, validator=validators.optional(validators.min_len(1)), metadata=url_parameter(APPLICATION_KEY)
    )
    version: str | None = None
    owner: str | None = attrs.field(default=None, metadata=url_parameter(OWNER_KEY))
    organization: str | None = attrs.field(default=None, metadata=url_parameter(ORGANIZATION_KEY))
    architecture: str | None = attrs.field(default=None, metadata=url_parameter(ARCHITECTURE_KEY))
    environment: str | None = attrs.field(default=None, metadata=url_parameter(ENVIRONMENT_KEY))
    metadata_type: MetadataType | None = None
    advertised_host: str | None = attrs.field(default=None, metadata=env_variable("DUBBO_IP_TO_REGISTRY"))
    advertised_port: int | None = attrs.field(
        default=None,
        validator=validators.optional([validators.ge(1), validators.le(65535)]),
        metadata=env_variable("DUBBO_PORT_TO_REGISTRY"),
    )


@attrs.define(frozen=True, kw_only=True)
class RegistryConfig:
    """Connect to one registry.

    Attributes:
        address: Registry URL; its scheme selects the registry implementation,
            as in ``zookeeper://127.0.0.1:2181``. A cluster lists further hosts
            after commas, as in ``zookeeper://zk1:2181,zk2:2181``. Query
            parameters reach the implementation.
        group: Keeps the data of the registry apart from that of others in
            the same cluster; in ZooKeeper, the root node of it, ``dubbo``
            by default.
        namespace: Nacos namespace ID that the data of the registry is in;
            ``None`` means ``public``. ZooKeeper ignores it.
        mode: How services register and providers are discovered;
            ``None`` means ``all``.
        register: Whether the application registers its services and
            references with the registry; ``None`` means it does.
        subscribe: Whether references discover providers through the
            registry; ``None`` means they do.
        preferred: Whether a reference of several registries calls the
            providers of this one while it has any.
        zone: Zone of the registry, which calls whose ``registry.zone``
            attachment names it go to first.
        weight: Share of the calls of a reference of several registries
            that go to this one, relative to the others; ``None`` means 100.
        parameters: Options for the implementation, such as ``session``, and
            for what is registered, such as ``simplified`` and
            ``extra-keys``, added to the URL query. They merge key by key
            across configuration layers, which a query string cannot.
        use_as_config_center: Whether the registry also serves as the
            configuration center when none is set; ``None`` lets the first
            registry whose kind can serve as one do so.

    Raises:
        ValueError: A parameter and a query parameter of the address, or
            either and a field that is set, set one key to different values.
    """

    address: str = attrs.field(validator=_address)
    group: str | None = attrs.field(default=None, metadata=url_parameter(GROUP_KEY))
    namespace: str | None = attrs.field(default=None, metadata=url_parameter(NAMESPACE_KEY))
    mode: RegistryMode | None = attrs.field(default=None, metadata=url_parameter(REGISTER_MODE_KEY))
    register: bool | None = attrs.field(default=None, metadata=url_parameter(REGISTER_KEY))
    subscribe: bool | None = attrs.field(default=None, metadata=url_parameter(SUBSCRIBE_KEY))
    preferred: bool | None = attrs.field(default=None, metadata=url_parameter(PREFERRED_KEY))
    zone: str | None = attrs.field(default=None, metadata=url_parameter(ZONE_KEY))
    weight: int | None = attrs.field(default=None, validator=_non_negative, metadata=url_parameter(WEIGHT_KEY))
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())
    use_as_config_center: bool | None = None

    def __attrs_post_init__(self) -> None:
        # Each key appears once in the URL that to_url builds.
        check_address_keys(self, self.parameters, _address_url(self.address).parameters)

    def to_url(self) -> URL:
        """Return the URL of the registry, which creates its implementations and says how to use it.

        The address keeps its query parameters, and the fields that are set
        and ``parameters`` are added.
        """
        url = _address_url(self.address)
        return url.replace(parameters={**to_url_parameters(self), **url.parameters})


@attrs.define(frozen=True, kw_only=True)
class TripleConfig:
    """Tune the Triple protocol, on the side whose configuration holds it.

    A protocol's settings tune its server; the consumer's and a reference's
    tune the calls they make. ``None`` leaves a value to the protocol, or for
    a reference, to the consumer.

    Attributes:
        max_receive_message_size: Bytes of the largest message received;
            ``None`` means 4 MiB.
        compressor: Name of the compression of the messages sent, such as
            ``gzip``; ``None`` sends them uncompressed. A server compresses
            only for callers that accept it.
        max_concurrent_streams: Calls the other side may run at once on one
            connection; ``None`` means 100.
        initial_window_size: Bytes the other side may send on one call
            before it waits for more credit; ``None`` means a window that
            starts at 1 MiB and grows with the bandwidth-delay product
            measured on the connection, up to 16 MiB.
        connection_initial_window_size: Bytes the other side may send on one
            connection before it waits for more credit; ``None`` means 16 MiB.
        max_header_list_size: Bytes of the largest header block received;
            ``None`` means 64 KiB.
        keep_alive_interval: Seconds without traffic before a PING checks
            the connection; ``None`` sends no PING.
        keep_alive_timeout: Seconds to wait for the PING acknowledgement
            before the connection closes; ``None`` means 20.
        connect_timeout: Seconds a caller waits for a connection to be
            established before the call fails as unavailable; ``None``
            means 3.
        health_enabled: Whether a server also serves
            ``grpc.health.v1.Health``; ``None`` means no.
        reflection_enabled: Whether a server also serves
            ``grpc.reflection.v1.ServerReflection`` and its earlier
            ``grpc.reflection.v1alpha``; ``None`` means no.
        parameters: Further options of the protocol and its transport, as
            text, such as ``stream-send-buffer-size``. A reference's merge key
            by key over the consumer's.

    The settings become URL parameters after ``triple.``, as in
    ``triple.compressor``.

    Raises:
        ValueError: A parameter is one that a field sets.
    """

    max_receive_message_size: int | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(MAX_RECEIVE_MESSAGE_SIZE_KEY)
    )
    compressor: str | None = attrs.field(default=None, metadata=url_parameter(COMPRESSOR_KEY))
    max_concurrent_streams: int | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(MAX_CONCURRENT_STREAMS_KEY)
    )
    initial_window_size: int | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(INITIAL_WINDOW_SIZE_KEY)
    )
    connection_initial_window_size: int | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(CONNECTION_INITIAL_WINDOW_SIZE_KEY)
    )
    max_header_list_size: int | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(MAX_HEADER_LIST_SIZE_KEY)
    )
    keep_alive_interval: float | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(KEEP_ALIVE_INTERVAL_KEY, to_milliseconds)
    )
    keep_alive_timeout: float | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(KEEP_ALIVE_TIMEOUT_KEY, to_milliseconds)
    )
    connect_timeout: float | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(CONNECT_TIMEOUT_KEY, to_milliseconds)
    )
    health_enabled: bool | None = attrs.field(default=None, metadata=url_parameter(HEALTH_ENABLED_KEY))
    reflection_enabled: bool | None = attrs.field(default=None, metadata=url_parameter(REFLECTION_ENABLED_KEY))
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())

    def __attrs_post_init__(self) -> None:
        check_url_keys(self, self.parameters)


@attrs.define(frozen=True, kw_only=True)
class DubboProtocolConfig:
    """Tune a ``dubbo`` server.

    ``None`` leaves a value to the protocol. The settings become the URL
    parameters other languages read, such as ``payload`` and ``heartbeat``.

    Attributes:
        payload: Bytes of the largest request or response body; ``None``
            means 8 MiB.
        heartbeat: Seconds of silence before a consumer sends a heartbeat,
            which also sets ``heartbeat_timeout``; ``None`` means 60.
        heartbeat_timeout: Seconds without reading before a connection
            closes; at least two heartbeats, ``None`` means three.
        max_concurrent_calls: Calls the server runs at once; one more is
            refused. ``None`` means 200, and 0 any number.
    """

    payload: int | None = attrs.field(default=None, validator=_positive, metadata=url_parameter(PAYLOAD_KEY))
    heartbeat: float | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(HEARTBEAT_KEY, to_milliseconds)
    )
    heartbeat_timeout: float | None = attrs.field(
        default=None, validator=_positive, metadata=url_parameter(HEARTBEAT_TIMEOUT_KEY, to_milliseconds)
    )
    max_concurrent_calls: int | None = attrs.field(
        default=None, validator=_non_negative, metadata=url_parameter(MAX_CONCURRENT_CALLS_KEY)
    )


@attrs.define(frozen=True, kw_only=True)
class ProtocolConfig:
    """Accept requests with one protocol.

    Attributes:
        name: Protocol name, such as ``tri``; it selects the implementation.
            ``None`` takes the key of the protocol in ``DubboConfig.protocols``,
            so that ``{"tri": ProtocolConfig(port=50051)}`` serves ``tri``.
        host: Address to listen on; ``None`` means ``0.0.0.0``, every IPv4
            interface.
        port: Port to listen on, 0 to let the operating system assign one, or
            ``None`` for the protocol's default: 50051 for ``tri``, 20880 for
            ``dubbo``.
        advertised_port: Port registered in place of the one it listens on,
            as behind NAT or a port mapping; ``None`` leaves it to
            ``application.advertised_port``.
        dubbo: Settings of a ``dubbo`` server.
        triple: Settings of a ``tri`` server.

    A protocol ignores the settings of the others.
    """

    name: str | None = attrs.field(default=None, validator=validators.optional(validators.min_len(1)))
    host: str | None = None
    port: int | None = attrs.field(
        default=None, validator=validators.optional([validators.ge(0), validators.le(65535)])
    )
    advertised_port: int | None = attrs.field(
        default=None, validator=validators.optional([validators.ge(1), validators.le(65535)])
    )
    dubbo: DubboProtocolConfig = attrs.field(factory=DubboProtocolConfig, metadata=url_nested())
    triple: TripleConfig = attrs.field(factory=TripleConfig, metadata=url_nested(TRIPLE_KEY))


@attrs.define(frozen=True, kw_only=True)
class MetadataReportConfig:
    """Where application-level discovery stores the metadata of instances and the applications that provide each interface, when not in the registries.

    The metadata of instances is stored there when
    ``application.metadata_type`` is ``remote``.

    Attributes:
        address: Metadata report URL; its scheme selects the implementation,
            as in ``zookeeper://127.0.0.1:2181``. A cluster lists further
            hosts after commas. Query parameters reach the implementation.
        group: Keeps the data apart from that of others in the same cluster;
            ``None`` leaves it to the implementation.
        namespace: Nacos namespace ID that the data is in; ``None`` means
            ``public``. ZooKeeper ignores it.
        parameters: Options for the implementation, such as ``timeout``,
            added to the URL query. They merge key by key across
            configuration layers, which a query string cannot.

    Raises:
        ValueError: A parameter and a query parameter of the address, or
            either and a field that is set, set one key to different values.
    """

    address: str = attrs.field(validator=_address)
    group: str | None = attrs.field(default=None, metadata=url_parameter(GROUP_KEY))
    namespace: str | None = attrs.field(default=None, metadata=url_parameter(NAMESPACE_KEY))
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())

    def __attrs_post_init__(self) -> None:
        # Each key appears once in the URL that to_url builds.
        check_address_keys(self, self.parameters, _address_url(self.address).parameters)

    def to_url(self) -> URL:
        """Return the URL of the metadata report, which creates its implementation.

        The address keeps its query parameters, and the fields that are set
        and ``parameters`` are added.
        """
        url = _address_url(self.address)
        return url.replace(parameters={**to_url_parameters(self), **url.parameters})


@attrs.define(frozen=True, kw_only=True)
class ConfigCenterConfig:
    """Read configuration from a configuration center at startup.

    The entry under the key ``config_file`` in ``group`` is read once. It ranks
    above the configuration sources and below environment variables and code.

    Attributes:
        address: Configuration center URL; its scheme selects the
            implementation, as in ``zookeeper://127.0.0.1:2181``. A cluster
            lists further hosts after commas. Query parameters reach the
            implementation.
        namespace: Isolates the entries of one environment; ``None`` leaves
            it to the implementation, such as ``dubbo`` for ZooKeeper, whose
            entries are under ``/{namespace}/config``.
        group: Group of the entry; ``None`` means ``dubbo``.
        config_file: Key of the entry; ``None`` means ``dubbo.yaml``.
        format: Name of the parser for the entry, such as ``yaml``; ``None``
            uses the suffix of ``config_file``.
        timeout: Seconds each operation of the implementation may take; must
            be positive; ``None`` means 30.
        check: Whether startup fails when the entry cannot be read; when
            false, startup continues without it. ``None`` means true.
        parameters: Options for the implementation, such as ``session``,
            added to the URL query. They merge key by key across
            configuration layers, which a query string cannot.

    Raises:
        ValueError: A parameter and a query parameter of the address, or
            either and a field that is set, set one key to different values.
    """

    address: str = attrs.field(validator=_address)
    namespace: str | None = attrs.field(default=None, metadata=url_parameter(NAMESPACE_KEY))
    group: str | None = None
    config_file: str | None = None
    format: str | None = None
    timeout: float | None = attrs.field(
        default=None,
        validator=_positive,
        metadata=url_parameter(TIMEOUT_KEY, to_milliseconds, default=DEFAULT_CONFIG_CENTER_TIMEOUT),
    )
    check: bool | None = None
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())

    @classmethod
    def from_registry(cls, registry: RegistryConfig) -> Self:
        """Return the configuration center that ``registry`` also serves as.

        It has the address and the options of the registry; the namespace of
        the registry, else its group, becomes its namespace, and a
        ``timeout`` option its timeout.

        Raises:
            ValueError: The ``timeout`` of the registry is not whole milliseconds.
        """
        url = _address_url(registry.address)
        parameters: dict[str, str] = {**url.parameters, **registry.parameters}
        timeout = parameters.pop(TIMEOUT_KEY, None)
        group = parameters.pop(GROUP_KEY, None) or registry.group
        namespace = parameters.pop(NAMESPACE_KEY, None) or registry.namespace
        return cls(
            address=url.replace(parameters={}).render_as_string(hide_secrets=False),
            namespace=namespace or group,
            timeout=None if timeout is None else milliseconds(timeout),
            parameters=parameters,
        )

    def __attrs_post_init__(self) -> None:
        # Each key appears once in the URL that to_url builds.
        check_address_keys(self, self.parameters, _address_url(self.address).parameters)

    def to_url(self) -> URL:
        """Return the URL that creates the implementation.

        The address keeps its query parameters, and the fields that become
        URL parameters, with their defaults when left as ``None`` and the
        address does not set them, and ``parameters`` are added.
        """
        url = _address_url(self.address)
        return url.replace(parameters={**to_url_parameters(self), **url.parameters})


@attrs.define(frozen=True, kw_only=True)
class MethodConfig:
    """Override call settings for one method.

    ``None`` inherits the value of the enclosing service or reference. A
    setting of the other side, such as ``retries`` of a service, does
    nothing.

    Attributes:
        timeout: Seconds a unary call may take before it fails; must be
            positive.
        retries: Additional attempts after a failed call, for a reference.
        loadbalance: Name of the load balance that chooses the provider of
            each call of the method, for a reference.
        sticky: Whether each call of the method goes to the provider the
            call before went to while that one is available, for a reference.
        weight: Share of the calls of the method a provider takes among its
            providers, relative to their weights, for a service; must not
            be negative.
        executes: Calls of the method a provider serves at once, for a
            service; one more fails as unavailable. ``None`` and 0 serve
            any number.
        tps: Calls of the method a provider serves in each ``tps_interval``,
            counted apart from the other methods, for a service; one more
            fails as unavailable.
        tps_interval: Seconds of each window ``tps`` counts calls in, for a
            service.
        deprecated: Whether consumers log a warning the first time they
            call the method, for a service.
        actives: Calls of the method a consumer makes to one provider at
            once, for a reference; one more waits for one of them to end, up
            to its timeout, then fails as unavailable. ``None`` and 0 make
            any number.
    """

    timeout: float | None = attrs.field(default=None, validator=_positive, metadata=_TIMEOUT)
    retries: int | None = attrs.field(default=None, validator=_non_negative, metadata=_RETRIES)
    loadbalance: str | None = attrs.field(default=None, metadata=_LOADBALANCE)
    sticky: bool | None = attrs.field(default=None, metadata=_STICKY)
    weight: int | None = attrs.field(default=None, validator=_non_negative, metadata=_WEIGHT)
    executes: int | None = attrs.field(default=None, validator=_non_negative, metadata=_EXECUTES)
    tps: int | None = attrs.field(default=None, validator=_non_negative, metadata=_TPS)
    tps_interval: float | None = attrs.field(default=None, validator=_positive, metadata=_TPS_INTERVAL)
    deprecated: bool | None = attrs.field(default=None, metadata=_DEPRECATED)
    actives: int | None = attrs.field(default=None, validator=_non_negative, metadata=_ACTIVES)


@attrs.define(frozen=True, kw_only=True)
class ServiceConfig:
    """Override provider defaults for one exposed service.

    The implementation is registered in code and matched to this entry by
    service name. ``None`` inherits the provider value.

    Attributes:
        group: Service group, part of the service identity.
        version: Service version, part of the service identity.
        timeout: Seconds a unary call may take before it fails; must be
            positive. Registries publish it to consumers that set none.
        weight: Share of the calls the service takes among its providers,
            relative to their weights; must not be negative. ``None`` weighs 100.
        warmup: Seconds after a provider registers over which its weight
            rises to the full; ``None`` means 600.
        tag: Tag of the service, which calls asking for it go to first.
        serialization: Name of the format the messages of the service are
            encoded in; ``None`` means protobuf over
            ``tri`` and hessian2 over ``dubbo``.
        registries: Names from ``DubboConfig.registries`` to register with.
        protocols: Names from ``DubboConfig.protocols`` to expose the service on.
        filters: Names of the filters each call to the service runs
            through, the first outermost, after those its settings add.
        token: Secret that each call must attach, which registries publish
            to consumers; true makes a random one, false requires none.
        accesslog: Whether each call is logged at INFO to the
            ``dubbo.accesslog`` logger.
        executes: Calls of each method served at once; one more fails as
            unavailable. ``None`` and 0 serve any number.
        tps: Calls served in each ``tps_interval``, counted over all methods
            but those that set their own; one more fails as unavailable.
            ``None`` and 0 serve any number.
        tps_interval: Seconds of each window ``tps`` counts calls in;
            ``None`` means 60.
        deprecated: Whether consumers log a warning the first time they
            call each method.
        parameters: Further URL parameters, below those the settings here
            produce.
        methods: Overrides keyed by method name.
    """

    group: str | None = attrs.field(default=None, metadata=_GROUP)
    version: str | None = attrs.field(default=None, metadata=_VERSION)
    timeout: float | None = attrs.field(default=None, validator=_positive, metadata=_TIMEOUT)
    weight: int | None = attrs.field(default=None, validator=_non_negative, metadata=_WEIGHT)
    warmup: float | None = attrs.field(default=None, validator=_non_negative, metadata=_WARMUP)
    tag: str | None = attrs.field(default=None, metadata=_TAG)
    serialization: str | None = attrs.field(default=None, metadata=_SERIALIZATION)
    registries: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    protocols: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_SERVICE_FILTERS)
    token: bool | str | None = attrs.field(default=None, validator=_token, metadata=_TOKEN)
    accesslog: bool | None = attrs.field(default=None, metadata=_ACCESSLOG)
    executes: int | None = attrs.field(default=None, validator=_non_negative, metadata=_EXECUTES)
    tps: int | None = attrs.field(default=None, validator=_non_negative, metadata=_TPS)
    tps_interval: float | None = attrs.field(default=None, validator=_positive, metadata=_TPS_INTERVAL)
    deprecated: bool | None = attrs.field(default=None, metadata=_DEPRECATED)
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())
    methods: dict[str, MethodConfig] = attrs.field(factory=dict, metadata=url_nested())

    def __attrs_post_init__(self) -> None:
        check_url_keys(self, self.parameters)


@attrs.define(frozen=True, kw_only=True)
class ReferenceConfig:
    """Override consumer defaults for one referenced service.

    ``None`` inherits the consumer value.

    Attributes:
        urls: Addresses of the providers to call directly instead of
            discovering them, as in ``tri://10.0.0.5:50051``; the scheme of
            each selects its protocol. A URL without a path calls the service
            by its name. Query parameters reach the protocol, below those the
            settings here produce. A reference with urls also calls the
            providers of the registries it sets itself, but not those of the
            consumer's.
        group: Group of the service to call.
        version: Version of the service to call.
        timeout: Seconds a unary call may take before it fails; must be
            positive. ``None`` takes the provider's, else 1.
        retries: Further attempts, on other providers, after an attempt fails
            with ``UNAVAILABLE``, as when none can take it; ``None`` means 2.
        cluster: Name of the cluster that makes each call through the
            providers; ``None`` means ``failover``, which makes the retries.
        loadbalance: Name of the load balance that chooses the provider of
            each call; ``None`` chooses at random by weight.
        sticky: Whether each call goes to the provider the call before went
            to while that one is available, the load balance choosing only
            when it is not; ``None`` means false.
        check: Whether startup fails with `RpcError` ``UNAVAILABLE`` when no
            provider is connected within 3 seconds; ``None`` means true.
        tag: Tag of the providers that calls go to first, when a call does
            not ask for one itself.
        serialization: Name of the format the messages of the calls are
            encoded in; ``None`` means protobuf over
            ``tri`` and hessian2 over ``dubbo``.
        registries: Names from ``DubboConfig.registries`` to discover providers
            in, besides those ``urls`` names.
        provided_by: Names of the applications that provide the service, for
            registries in ``instance`` or ``all`` mode; ``None`` looks
            them up in the registry.
        triple: Settings of calls over ``tri``; ``None`` fields take the consumer's.
        filters: Names of the filters each call runs through, the first
            outermost, once per call whatever the retries.
        attempt_filters: Names of the filters each attempt of a call runs
            through, the first outermost, on the provider it goes to, after
            those the settings add.
        routers: Names of the routers that narrow the providers of each
            call, in order; ``None`` takes the consumer's.
        actives: Calls of each method made to one provider at once; one
            more waits for one of them to end, up to its timeout, then fails
            as unavailable. ``None`` and 0 make any number.
        parameters: Further URL parameters, below those the settings here
            produce.
        methods: Overrides keyed by method name.
    """

    urls: tuple[str, ...] | None = attrs.field(default=None, validator=_urls)
    group: str | None = attrs.field(default=None, metadata=_GROUP)
    version: str | None = attrs.field(default=None, metadata=_VERSION)
    timeout: float | None = attrs.field(default=None, validator=_positive, metadata=_TIMEOUT)
    retries: int | None = attrs.field(default=None, validator=_non_negative, metadata=_RETRIES)
    cluster: str | None = attrs.field(default=None, metadata=_CLUSTER)
    loadbalance: str | None = attrs.field(default=None, metadata=_LOADBALANCE)
    sticky: bool | None = attrs.field(default=None, metadata=_STICKY)
    check: bool | None = attrs.field(default=None, metadata=_CHECK)
    tag: str | None = attrs.field(default=None, metadata=_TAG)
    serialization: str | None = attrs.field(default=None, metadata=_SERIALIZATION)
    registries: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    provided_by: tuple[str, ...] | None = attrs.field(
        default=None, validator=_names, metadata=url_parameter(PROVIDED_BY_KEY, ",".join)
    )
    triple: TripleConfig = attrs.field(factory=TripleConfig, metadata=url_nested(TRIPLE_KEY))
    filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_REFERENCE_FILTERS)
    attempt_filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_ATTEMPT_FILTERS)
    routers: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_ROUTERS)
    actives: int | None = attrs.field(default=None, validator=_non_negative, metadata=_ACTIVES)
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())
    methods: dict[str, MethodConfig] = attrs.field(factory=dict, metadata=url_nested())

    def __attrs_post_init__(self) -> None:
        check_url_keys(self, self.parameters)


@attrs.define(frozen=True, kw_only=True)
class ProviderConfig:
    """Defaults for every exposed service, with per-service overrides.

    Attributes:
        group: Service group, part of the service identity.
        version: Service version, part of the service identity.
        timeout: Seconds a unary call may take before it fails; must be
            positive. Registries publish it to consumers that set none.
        weight: Share of the calls each service takes among its providers,
            relative to their weights; must not be negative. ``None`` weighs 100.
        warmup: Seconds after a provider registers over which its weight
            rises to the full; ``None`` means 600.
        tag: Tag of the services, which calls asking for it go to first.
        serialization: Name of the format the messages of the services are
            encoded in; ``None`` means protobuf over
            ``tri`` and hessian2 over ``dubbo``.
        registries: Names from ``DubboConfig.registries`` to register with;
            ``None`` uses all of them.
        protocols: Names from ``DubboConfig.protocols`` to expose services on;
            ``None`` uses all of them.
        filters: Names of the filters each call to a service runs through,
            the first outermost, after those its settings add; ``None`` runs
            no others.
        token: Secret that each call must attach, which registries publish
            to consumers; true makes a random one, false requires none.
        accesslog: Whether each call is logged at INFO to the
            ``dubbo.accesslog`` logger.
        executes: Calls of each method served at once; one more fails as
            unavailable. ``None`` and 0 serve any number.
        tps: Calls served in each ``tps_interval``, counted over all methods
            but those that set their own; one more fails as unavailable.
            ``None`` and 0 serve any number.
        tps_interval: Seconds of each window ``tps`` counts calls in;
            ``None`` means 60.
        parameters: Further URL parameters, below those the settings here
            produce.
        services: Overrides keyed by service name.
    """

    group: str | None = attrs.field(default=None, metadata=_GROUP)
    version: str | None = attrs.field(default=None, metadata=_VERSION)
    timeout: float | None = attrs.field(default=None, validator=_positive, metadata=_TIMEOUT)
    weight: int | None = attrs.field(default=None, validator=_non_negative, metadata=_WEIGHT)
    warmup: float | None = attrs.field(default=None, validator=_non_negative, metadata=_WARMUP)
    tag: str | None = attrs.field(default=None, metadata=_TAG)
    serialization: str | None = attrs.field(default=None, metadata=_SERIALIZATION)
    registries: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    protocols: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_SERVICE_FILTERS)
    token: bool | str | None = attrs.field(default=None, validator=_token, metadata=_TOKEN)
    accesslog: bool | None = attrs.field(default=None, metadata=_ACCESSLOG)
    executes: int | None = attrs.field(default=None, validator=_non_negative, metadata=_EXECUTES)
    tps: int | None = attrs.field(default=None, validator=_non_negative, metadata=_TPS)
    tps_interval: float | None = attrs.field(default=None, validator=_positive, metadata=_TPS_INTERVAL)
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())
    services: dict[str, ServiceConfig] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
        check_url_keys(self, self.parameters)


@attrs.define(frozen=True, kw_only=True)
class ConsumerConfig:
    """Defaults for every referenced service, with per-reference overrides.

    Attributes:
        group: Group of the services to call.
        version: Version of the services to call.
        timeout: Seconds a unary call may take before it fails; must be
            positive. ``None`` takes the provider's, else 1.
        retries: Further attempts, on other providers, after an attempt fails
            with ``UNAVAILABLE``, as when none can take it; ``None`` means 2.
        cluster: Name of the cluster that makes each call through the
            providers; ``None`` means ``failover``, which makes the retries.
        loadbalance: Name of the load balance that chooses the provider of
            each call; ``None`` chooses at random by weight.
        sticky: Whether each call goes to the provider the call before went
            to while that one is available, the load balance choosing only
            when it is not; ``None`` means false.
        check: Whether startup fails with `RpcError` ``UNAVAILABLE`` when no
            provider is connected within 3 seconds; ``None`` means true.
        tag: Tag of the providers that calls go to first, when a call does
            not ask for one itself.
        serialization: Name of the format the messages of the calls are
            encoded in; ``None`` means protobuf over
            ``tri`` and hessian2 over ``dubbo``.
        registries: Names from ``DubboConfig.registries`` to discover providers
            in; ``None`` uses all of them. References that set ``urls`` use none.
        triple: Settings of calls over ``tri``.
        filters: Names of the filters each call runs through, the first
            outermost, once per call whatever the retries; ``None`` runs none.
        attempt_filters: Names of the filters each attempt of a call runs
            through, the first outermost, on the provider it goes to, after
            those the settings add; ``None`` runs no others.
        routers: Names of the routers that narrow the providers of each
            call, in order; ``None`` runs ``tag``, then ``condition``.
        actives: Calls of each method made to one provider at once; one
            more waits for one of them to end, up to its timeout, then fails
            as unavailable. ``None`` and 0 make any number.
        parameters: Further URL parameters, below those the settings here
            produce.
        references: Overrides keyed by service name.
    """

    group: str | None = attrs.field(default=None, metadata=_GROUP)
    version: str | None = attrs.field(default=None, metadata=_VERSION)
    timeout: float | None = attrs.field(default=None, validator=_positive, metadata=_TIMEOUT)
    retries: int | None = attrs.field(default=None, validator=_non_negative, metadata=_RETRIES)
    cluster: str | None = attrs.field(default=None, metadata=_CLUSTER)
    loadbalance: str | None = attrs.field(default=None, metadata=_LOADBALANCE)
    sticky: bool | None = attrs.field(default=None, metadata=_STICKY)
    check: bool | None = attrs.field(default=None, metadata=_CHECK)
    tag: str | None = attrs.field(default=None, metadata=_TAG)
    serialization: str | None = attrs.field(default=None, metadata=_SERIALIZATION)
    registries: tuple[str, ...] | None = attrs.field(default=None, validator=_names)
    triple: TripleConfig = attrs.field(factory=TripleConfig, metadata=url_nested(TRIPLE_KEY))
    filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_REFERENCE_FILTERS)
    attempt_filters: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_ATTEMPT_FILTERS)
    routers: tuple[str, ...] | None = attrs.field(default=None, validator=_names, metadata=_ROUTERS)
    actives: int | None = attrs.field(default=None, validator=_non_negative, metadata=_ACTIVES)
    parameters: dict[str, str] = attrs.field(factory=dict, validator=_parameters, metadata=url_nested())
    references: dict[str, ReferenceConfig] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
        check_url_keys(self, self.parameters)


@attrs.define(frozen=True, kw_only=True)
class ShutdownConfig:
    """How the application stops.

    It first tells callers it is stopping and leaves the registries, then
    keeps serving for ``unregister_wait``, so that callers notice and turn
    to other providers. It then stops taking calls and lets the running
    ones, served and made, finish before cancelling them. All of it takes
    at most ``grace``; what still runs then is cancelled. An application
    whose task is cancelled stops at once, without these waits.

    Attributes:
        unregister_wait: Seconds the services keep serving after they leave
            the registries; ``None`` waits 3, and nothing is waited for
            without registries.
        grace: Seconds stopping may take in all; ``None`` means 10. A server
            waits at most as long for its running calls.
    """

    unregister_wait: float | None = attrs.field(default=None, validator=_non_negative)
    grace: float | None = attrs.field(
        default=None, validator=_non_negative, metadata=url_parameter(SHUTWAIT_KEY, to_milliseconds)
    )


@attrs.define(frozen=True, kw_only=True)
class TLSConfig:
    """Secure with TLS the connections the application serves and those it opens.

    Servers and clients each build a TLS context from the files, unless code
    gives that side a context, which is used as it is. For ``tri`` it must
    offer ALPN ``h2``, as ``context.set_alpn_protocols(["h2"])`` does. Code
    may give the files as paths, which are kept as text.

    Attributes:
        certfile: PEM file of the certificate chain to present, which a
            server requires and a client presents when asked.
        keyfile: PEM file of the private key of ``certfile``; ``None`` when
            ``certfile`` holds it.
        cafile: PEM file of the certificates to trust. A client trusts them
            instead of the system certificates; a server with them requires
            each client to present a certificate they sign.
        server_hostname: Name a client checks the server certificate carries;
            ``None`` takes the host of the provider.
        server_context: Context of the servers, in place of the files; only
            code can set it.
        client_context: Context of the clients, in place of the files; only
            code can set it.
    """

    certfile: str | None = attrs.field(
        default=None, converter=converters.optional(os.fspath), metadata=url_parameter(TLS_CERT_FILE_KEY)
    )
    keyfile: str | None = attrs.field(
        default=None, converter=converters.optional(os.fspath), metadata=url_parameter(TLS_KEY_FILE_KEY)
    )
    cafile: str | None = attrs.field(
        default=None, converter=converters.optional(os.fspath), metadata=url_parameter(CA_CERT_FILE_KEY)
    )
    server_hostname: str | None = attrs.field(default=None, metadata=url_parameter(TLS_SERVER_NAME_KEY))
    server_context: ssl.SSLContext | None = attrs.field(
        default=None, validator=validators.optional(validators.instance_of(ssl.SSLContext))
    )
    client_context: ssl.SSLContext | None = attrs.field(
        default=None, validator=validators.optional(validators.instance_of(ssl.SSLContext))
    )


@attrs.define(frozen=True, kw_only=True)
class DubboConfig:
    """The complete configuration of one Dubbo application.

    Attributes:
        application: Identity of this application.
        registries: Registries keyed by the names that providers, services,
            consumers and references select them by.
        protocols: Protocols keyed by the names that providers and services
            select them by; ``tri`` with its defaults when none is defined.
        provider: Settings for services this application exposes.
        consumer: Settings for services this application calls.
        config_center: Where to read further configuration and the rules
            that change calls; ``None`` uses a registry that serves as one,
            if any.
        metadata_report: Where application-level discovery stores metadata
            and the applications of each interface; ``None`` stores them in
            each registry.
        tls: TLS of the connections the application serves and opens;
            ``None`` leaves them in cleartext.
        shutdown: How the application stops.

    Raises:
        ValueError: A registry is defined but ``application.name`` is not;
            a provider, service, consumer or reference selects a registry or
            protocol that is not defined; or ``application.advertised_port``
            would be registered for several protocols, which cannot share
            one port.
    """

    application: ApplicationConfig = attrs.field(factory=ApplicationConfig)
    registries: dict[str, RegistryConfig] = attrs.field(factory=dict)
    protocols: dict[str, ProtocolConfig] = attrs.field(
        factory=lambda: {DEFAULT_PROTOCOL: ProtocolConfig(name=DEFAULT_PROTOCOL)}
    )
    provider: ProviderConfig = attrs.field(factory=ProviderConfig)
    consumer: ConsumerConfig = attrs.field(factory=ConsumerConfig)
    config_center: ConfigCenterConfig | None = None
    metadata_report: MetadataReportConfig | None = None
    tls: TLSConfig | None = None
    shutdown: ShutdownConfig = attrs.field(factory=ShutdownConfig)

    def __attrs_post_init__(self) -> None:
        if self.registries and self.application.name is None:
            raise ValueError("application.name is required once a registry is defined")
        if self.application.advertised_port is not None:
            sharing = [name for name, protocol in self.protocols.items() if protocol.advertised_port is None]
            if len(sharing) > 1:
                raise ValueError(
                    f"application.advertised_port would be registered for the protocols {', '.join(map(repr, sharing))}; "
                    "set advertised_port on each of them"
                )

        # Field validators see one value; selected names refer to other sections.
        provider, consumer = self.provider, self.consumer
        _check_names("provider", provider.registries, self.registries, "registry")
        _check_names("provider", provider.protocols, self.protocols, "protocol")
        for name, service in provider.services.items():
            _check_names(f"service {name!r}", service.registries, self.registries, "registry")
            _check_names(f"service {name!r}", service.protocols, self.protocols, "protocol")

        _check_names("consumer", consumer.registries, self.registries, "registry")
        for name, reference in consumer.references.items():
            _check_names(f"reference {name!r}", reference.registries, self.registries, "registry")


def _check_names(owner: str, selected: tuple[str, ...] | None, defined: Mapping[str, object], kind: str) -> None:
    for name in selected or ():
        if name not in defined:
            raise ValueError(f"{owner} selects undefined {kind} {name!r}")
