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

"""Dubbo vocabulary shared with other languages, and the defaults of the framework.

Three groups of names live here, in this order:

- ``*_KEY``: the key of a URL parameter or a call attachment that Dubbo
  implementations in other languages share.
- Values: what is neither a key nor a default, such as the name of a
  built-in implementation that other languages share.
- ``DEFAULT_*``: the value a configuration field left as ``None``, or a URL
  that leaves out its parameter, stands for.

Constants private to one module stay in that module. Within each group
names are sorted; a comment gives only what the name cannot, such as a unit
or the values it takes. A time in a URL parameter is whole milliseconds; a
``DEFAULT_*`` time, like the configuration field it stands for, is seconds.
"""

from collections.abc import Mapping
from types import MappingProxyType

__all__ = [
    "ACCESSLOG_KEY",
    "ACCESS_KEY_KEY",
    "ACTIVES_KEY",
    "APPLICATION_KEY",
    "ARCHITECTURE_KEY",
    "BACKUP_KEY",
    "BROADCAST_FAIL_PERCENT_KEY",
    "CATEGORY_KEY",
    "CA_CERT_FILE_KEY",
    "CHECK_KEY",
    "CLIENT_KEY",
    "CLUSTER_KEY",
    "COMPRESSOR_KEY",
    "CONNECTION_INITIAL_WINDOW_SIZE_KEY",
    "CONNECT_TIMEOUT_KEY",
    "CONSUMERS_CATEGORY",
    "DEFAULT_CHECK",
    "DEFAULT_CLUSTER",
    "DEFAULT_CONFIG_CENTER_CHECK",
    "DEFAULT_CONFIG_CENTER_FILE",
    "DEFAULT_CONFIG_CENTER_GROUP",
    "DEFAULT_CONFIG_CENTER_TIMEOUT",
    "DEFAULT_CONNECTION_INITIAL_WINDOW_SIZE",
    "DEFAULT_CONNECT_TIMEOUT",
    "DEFAULT_DUBBO_PORT",
    "DEFAULT_FORKS",
    "DEFAULT_GENERIC",
    "DEFAULT_HEARTBEAT",
    "DEFAULT_INITIAL_WINDOW_SIZE",
    "DEFAULT_JAVA_SERIALIZATION",
    "DEFAULT_KEEP_ALIVE_TIMEOUT",
    "DEFAULT_LOADBALANCE",
    "DEFAULT_MAX_CONCURRENT_CALLS",
    "DEFAULT_MAX_CONCURRENT_STREAMS",
    "DEFAULT_MAX_HEADER_LIST_SIZE",
    "DEFAULT_MAX_RECEIVE_MESSAGE_SIZE",
    "DEFAULT_METADATA_TYPE",
    "DEFAULT_PAYLOAD",
    "DEFAULT_PROTOCOL",
    "DEFAULT_PROTOCOL_HOST",
    "DEFAULT_REGISTER",
    "DEFAULT_REGISTRY_MODE",
    "DEFAULT_RETRIES",
    "DEFAULT_ROOT",
    "DEFAULT_ROUTERS",
    "DEFAULT_SERIALIZATION",
    "DEFAULT_SHUTWAIT",
    "DEFAULT_STICKY",
    "DEFAULT_SUBSCRIBE",
    "DEFAULT_TIMEOUT",
    "DEFAULT_TPS_INTERVAL",
    "DEFAULT_TRIPLE_PORT",
    "DEFAULT_UNREGISTER_WAIT",
    "DEFAULT_WARMUP",
    "DEFAULT_WEIGHT",
    "DEPRECATED_KEY",
    "DUBBO_VERSION",
    "DUBBO_VERSION_KEY",
    "ENDPOINTS_KEY",
    "ENVIRONMENT_KEY",
    "EXECUTES_KEY",
    "EXTRA_KEYS_KEY",
    "FAILBACK_TASKS_KEY",
    "FORCE_TAG_KEY",
    "FORKS_KEY",
    "GENERIC_KEY",
    "GROUP_KEY",
    "HASH_ARGUMENTS_KEY",
    "HASH_NODES_KEY",
    "HEALTH_ENABLED_KEY",
    "HEARTBEAT_KEY",
    "HEARTBEAT_TIMEOUT_KEY",
    "INITIAL_WINDOW_SIZE_KEY",
    "INTERFACE_KEY",
    "KEEP_ALIVE_INTERVAL_KEY",
    "KEEP_ALIVE_TIMEOUT_KEY",
    "LEAST_ACTIVE_LOADBALANCE",
    "LOADBALANCE_KEY",
    "MAX_CONCURRENT_CALLS_KEY",
    "MAX_CONCURRENT_STREAMS_KEY",
    "MAX_HEADER_LIST_SIZE_KEY",
    "MAX_RECEIVE_MESSAGE_SIZE_KEY",
    "METADATA_REVISION_KEY",
    "METADATA_SERVICE_URL_PARAMS_KEY",
    "METADATA_SERVICE_VERSION_KEY",
    "METADATA_STORAGE_TYPE_KEY",
    "METHODS_KEY",
    "NAMESPACE_KEY",
    "ORGANIZATION_KEY",
    "OWNER_KEY",
    "PATH_KEY",
    "PAYLOAD_KEY",
    "PREFERRED_KEY",
    "PREFER_SERIALIZATION_KEY",
    "PROVIDED_BY_KEY",
    "PROVIDERS_CATEGORY",
    "REFERENCE_FILTER_KEY",
    "REFLECTION_ENABLED_KEY",
    "REGISTER_KEY",
    "REGISTER_MODE_KEY",
    "REGISTRY_PREFERRED_KEY",
    "REGISTRY_ZONE_FORCE_KEY",
    "REGISTRY_ZONE_KEY",
    "RELEASE_KEY",
    "REMOTE_APPLICATION_KEY",
    "RETRIES_KEY",
    "ROUTER_KEY",
    "SECRET_KEY_KEY",
    "SERIALIZATION_IDS",
    "SERIALIZATION_KEY",
    "SERVER_KEY",
    "SERVICE_FILTER_KEY",
    "SESSION_KEY",
    "SHUTWAIT_KEY",
    "SIDE_KEY",
    "SIMPLIFIED_KEY",
    "SSL_ENABLED_KEY",
    "STICKY_KEY",
    "SUBSCRIBE_KEY",
    "TAG_KEY",
    "TIMEOUT_KEY",
    "TIMESTAMP_KEY",
    "TLS_CERT_FILE_KEY",
    "TLS_KEY_FILE_KEY",
    "TLS_SERVER_NAME_KEY",
    "TOKEN_KEY",
    "TPS_INTERVAL_KEY",
    "TPS_KEY",
    "TRIPLE_KEY",
    "VERSION_KEY",
    "WARMUP_KEY",
    "WEIGHT_KEY",
    "ZONE_AWARE_CLUSTER",
    "ZONE_KEY",
]

# ── Keys ─────────────────────────────────────────────────────────────────

# Keys of URL parameters.
ACCESSLOG_KEY = "accesslog"  # "true" logs each call a provider serves.
ACCESS_KEY_KEY = "accessKey"  # Key that signs the requests to a registry or configuration center, such as Nacos.
ACTIVES_KEY = "actives"  # Calls of a method a consumer makes to one provider at once.
APPLICATION_KEY = "application"  # Name of the application that calls or serves.
ARCHITECTURE_KEY = "architecture"  # Architecture of the application, as its owners describe it.
BACKUP_KEY = "backup"  # Further hosts of a cluster, separated by commas.
BROADCAST_FAIL_PERCENT_KEY = (
    "broadcast.fail.percent"  # Failures, as a percentage of the providers, that stop a broadcast.
)
CHECK_KEY = "check"  # "false" lets a reference start without a provider.
CLIENT_KEY = "client"  # Name of the client implementation.
CLUSTER_KEY = "cluster"
DEPRECATED_KEY = "deprecated"  # "true" on a service or method that consumers are warned about.
ENVIRONMENT_KEY = "environment"  # Environment the application runs in, such as "test" or "product".
EXECUTES_KEY = "executes"  # Calls of a method a provider serves at once.
FAILBACK_TASKS_KEY = "failbacktasks"  # Failed calls that may wait at once to be made again.
FORKS_KEY = "forks"  # Providers the forking cluster calls at once.
GENERIC_KEY = "generic"  # The mode of a call that names its method without a contract, such as "true".
GROUP_KEY = "group"  # Part of the service identity.
HASH_ARGUMENTS_KEY = "hash.arguments"  # Indexes of the arguments a call hashes, separated by commas.
HASH_NODES_KEY = "hash.nodes"  # Points of each provider on the ring of consistent hashing.
LOADBALANCE_KEY = "loadbalance"
NAMESPACE_KEY = "namespace"  # Isolates the data of a registry or configuration center.
ORGANIZATION_KEY = "organization"  # Organization that owns the application.
OWNER_KEY = "owner"  # People responsible for the application, separated by commas.
PROVIDED_BY_KEY = "provided-by"  # Applications that provide a referenced service, separated by commas.
REFERENCE_FILTER_KEY = "reference.filter"  # Filters of a reference, separated by commas.
RETRIES_KEY = "retries"  # Attempts after a failed one that a call may make.
ROUTER_KEY = "router"  # Routers of a reference, separated by commas.
SECRET_KEY_KEY = "secretKey"  # Secret of "accessKey".
SERIALIZATION_KEY = "serialization"
SERVER_KEY = "server"  # Name of the server implementation.
SERVICE_FILTER_KEY = "service.filter"  # Filters of a service, separated by commas.
SESSION_KEY = "session"  # Milliseconds a ZooKeeper session survives without a connection.
SHUTWAIT_KEY = "shutwait"  # Milliseconds a closing server waits for running requests.
STICKY_KEY = "sticky"  # "true" calls the provider of the call before while it is available.
TIMEOUT_KEY = "timeout"  # Milliseconds.
TOKEN_KEY = "token"  # Secret a provider registers, which each call to it attaches.
TPS_INTERVAL_KEY = "tps.interval"  # Milliseconds of each window that "tps" counts calls in.
TPS_KEY = "tps"  # Calls a provider serves in each window.
VERSION_KEY = "version"  # Part of the service identity.
WARMUP_KEY = "warmup"  # Milliseconds after it registers over which a provider's weight rises to the full.
WEIGHT_KEY = "weight"  # Share of the calls a provider takes, relative to the others.

# Keys of the URLs that registries hold.
CATEGORY_KEY = "category"  # "providers", "consumers", "routers" or "configurators".
DUBBO_VERSION_KEY = "dubbo"  # Version of the Dubbo protocol model, DUBBO_VERSION.
INTERFACE_KEY = "interface"
METHODS_KEY = "methods"  # Separated by commas.
PATH_KEY = "path"  # Interface a Dubbo request calls, among its attachments.
RELEASE_KEY = "release"  # Version of the framework that registered the URL.
REMOTE_APPLICATION_KEY = "remote.application"  # On the URL a consumer calls a provider with.
SIDE_KEY = "side"  # "provider" or "consumer".
TIMESTAMP_KEY = "timestamp"  # Milliseconds since the epoch when the URL was registered.

# Keys of registry URLs.
EXTRA_KEYS_KEY = "extra-keys"  # Further parameters, separated by commas, that simplified URLs keep.
PREFERRED_KEY = "preferred"  # "true" on the registry whose providers a reference calls first.
REGISTER_KEY = "register"  # "false" registers nothing with the registry.
REGISTER_MODE_KEY = "register-mode"  # "interface", "instance" or "all".
SIMPLIFIED_KEY = "simplified"  # "true" registers URLs with only the parameters consumers need.
SUBSCRIBE_KEY = "subscribe"  # "false" discovers no providers in the registry.
ZONE_KEY = "zone"

# Keys of the metadata of the application instances that registries hold.
ENDPOINTS_KEY = "dubbo.endpoints"  # JSON: the port of each protocol it serves.
METADATA_REVISION_KEY = "dubbo.metadata.revision"
METADATA_SERVICE_URL_PARAMS_KEY = "dubbo.metadata-service.url-params"  # JSON: protocol and port of its MetadataService.
METADATA_SERVICE_VERSION_KEY = "meta-v"  # "2.0.0" for MetadataServiceV2.
METADATA_STORAGE_TYPE_KEY = "dubbo.metadata.storage-type"  # "local" or "remote".

# Keys of tag routing, on provider and consumer URLs and in call attachments.
FORCE_TAG_KEY = "dubbo.force.tag"  # "true" fails a call that finds no provider of its tag.
TAG_KEY = "dubbo.tag"

# Keys that choose among the registries of a reference, on the invoker of each registry and in call attachments.
REGISTRY_PREFERRED_KEY = "registry.preferred"  # "true" on the invoker of the registry tried first.
REGISTRY_ZONE_FORCE_KEY = "registry.zone.force"  # "true" fails a call that finds no registry in its zone.
REGISTRY_ZONE_KEY = "registry.zone"

# Keys of Triple settings, each after TRIPLE_KEY and a dot, as in "triple.compressor".
COMPRESSOR_KEY = "compressor"  # Of the messages a caller or server sends.
CONNECTION_INITIAL_WINDOW_SIZE_KEY = "connection-initial-window-size"  # Bytes.
CONNECT_TIMEOUT_KEY = "connect-timeout"  # Milliseconds a caller waits for a connection to be established.
HEALTH_ENABLED_KEY = "health-enabled"  # "true" serves grpc.health.v1.Health.
INITIAL_WINDOW_SIZE_KEY = "initial-window-size"  # Bytes, for each stream.
KEEP_ALIVE_INTERVAL_KEY = "keep-alive-interval"  # Milliseconds without traffic before a PING.
KEEP_ALIVE_TIMEOUT_KEY = "keep-alive-timeout"  # Milliseconds to wait for the PING acknowledgement.
MAX_CONCURRENT_STREAMS_KEY = "max-concurrent-streams"
MAX_HEADER_LIST_SIZE_KEY = "max-header-list-size"  # Bytes.
MAX_RECEIVE_MESSAGE_SIZE_KEY = "max-receive-message-size"  # Bytes of the largest message a server or caller receives.
REFLECTION_ENABLED_KEY = "reflection-enabled"  # "true" serves grpc.reflection.v1 and v1alpha ServerReflection.
TRIPLE_KEY = "triple"

# Keys of Dubbo protocol settings.
HEARTBEAT_KEY = "heartbeat"  # Milliseconds without traffic before a consumer sends a heartbeat.
HEARTBEAT_TIMEOUT_KEY = "heartbeat.timeout"  # Milliseconds without reading before a connection is closed.
MAX_CONCURRENT_CALLS_KEY = "max-concurrent-calls"  # Calls a Dubbo server runs at once, 0 for any number.
PAYLOAD_KEY = "payload"  # Bytes of the largest body a request or response may have.
PREFER_SERIALIZATION_KEY = "prefer.serialization"  # Serializations a consumer should use, preferred first.

# Keys of TLS settings.
CA_CERT_FILE_KEY = "ca-cert-file"  # PEM file of the certificates to trust.
SSL_ENABLED_KEY = "ssl-enabled"  # "true" enables TLS.
TLS_CERT_FILE_KEY = "tls-cert-file"  # PEM file of the own certificate chain.
TLS_KEY_FILE_KEY = "tls-key-file"  # PEM file of the own private key.
TLS_SERVER_NAME_KEY = "tls-server-name"  # Name the server certificate must carry.

# ── Values ───────────────────────────────────────────────────────────────

CONSUMERS_CATEGORY = "consumers"  # The category of the URLs that consumers register.
DUBBO_VERSION = "2.0.2"  # Version of the Dubbo protocol model that calls and registered URLs carry.
LEAST_ACTIVE_LOADBALANCE = "leastactive"  # Chooses the provider with the fewest calls under way.
PROVIDERS_CATEGORY = "providers"  # The category of the URLs that providers register.
# The id of each serialization in the header of a Dubbo frame.
SERIALIZATION_IDS: Mapping[str, int] = MappingProxyType({"fastjson2": 23, "hessian2": 2})
ZONE_AWARE_CLUSTER = "zone-aware"  # Chooses among the registries of a reference.

# ── Defaults ─────────────────────────────────────────────────────────────

# Of the application and its registries.
DEFAULT_METADATA_TYPE = "local"  # Consumers ask each instance.
DEFAULT_REGISTER = True
DEFAULT_REGISTRY_MODE = "all"  # Register and discover both by interface and by instance.
DEFAULT_ROOT = "dubbo"  # The ZooKeeper node a registry, metadata report or configuration center keeps its nodes under.
DEFAULT_SUBSCRIBE = True

# Of protocols and services.
DEFAULT_CONNECTION_INITIAL_WINDOW_SIZE = 16 * 1024 * 1024  # Bytes.
DEFAULT_CONNECT_TIMEOUT = 3.0  # Seconds.
DEFAULT_DUBBO_PORT = 20880
DEFAULT_GENERIC = "true"  # Objects travel as maps naming their Java class under "class".
DEFAULT_HEARTBEAT = 60.0  # Seconds.
# Bytes a stream window starts at, before it grows with the bandwidth-delay product measured on the connection.
DEFAULT_INITIAL_WINDOW_SIZE = 1024 * 1024
DEFAULT_JAVA_SERIALIZATION = "hessian2"  # Where values travel as Java objects, as in the Dubbo protocol.
DEFAULT_KEEP_ALIVE_TIMEOUT = 20.0  # Seconds.
DEFAULT_MAX_CONCURRENT_CALLS = 200
DEFAULT_MAX_CONCURRENT_STREAMS = 100
DEFAULT_MAX_HEADER_LIST_SIZE = 64 * 1024  # Bytes.
DEFAULT_MAX_RECEIVE_MESSAGE_SIZE = 4 * 1024 * 1024  # Bytes.
DEFAULT_PAYLOAD = 8 * 1024 * 1024  # Bytes.
DEFAULT_PROTOCOL = "tri"  # The protocol DubboConfig has when it defines none.
DEFAULT_PROTOCOL_HOST = "0.0.0.0"  # Every IPv4 interface.
DEFAULT_SERIALIZATION = "protobuf"
DEFAULT_SHUTWAIT = 10.0  # Seconds.
DEFAULT_TPS_INTERVAL = 60.0  # Seconds.
DEFAULT_TRIPLE_PORT = 50051
DEFAULT_UNREGISTER_WAIT = 3.0  # Seconds.
DEFAULT_WARMUP = 600.0  # Seconds.
DEFAULT_WEIGHT = 100

# Of references.
DEFAULT_CHECK = True  # Startup fails without a provider.
DEFAULT_CLUSTER = "failover"
DEFAULT_FORKS = 2
DEFAULT_LOADBALANCE = "random"
DEFAULT_RETRIES = 2
DEFAULT_ROUTERS = ("tag", "condition")
DEFAULT_STICKY = False
DEFAULT_TIMEOUT = 1.0  # Seconds a unary call may take.

# Of the configuration center.
DEFAULT_CONFIG_CENTER_CHECK = True
DEFAULT_CONFIG_CENTER_FILE = "dubbo.yaml"
DEFAULT_CONFIG_CENTER_GROUP = "dubbo"
DEFAULT_CONFIG_CENTER_TIMEOUT = 30.0  # Seconds.
