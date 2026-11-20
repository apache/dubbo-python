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

import ssl

import attrs
import pytest

from dubbo.config import (
    ApplicationConfig,
    ConfigError,
    ConsumerConfig,
    DubboConfig,
    DubboProtocolConfig,
    MetadataReportConfig,
    MethodConfig,
    ProtocolConfig,
    ProviderConfig,
    ReferenceConfig,
    RegistryConfig,
    ServiceConfig,
    ShutdownConfig,
    TLSConfig,
    TripleConfig,
)
from dubbo.config.urls import (
    direct_urls,
    internal_service_urls,
    reference_registries,
    reference_url,
    service_registries,
    service_urls,
)
from dubbo.extension import ApplicationScope
from dubbo.rpc.definition import Method, Service
from dubbo.url import (
    ADVERTISED_PORT,
    APPLICATION_SCOPE,
    METADATA_CONSUMER_URL,
    METADATA_REPORT_URL,
    PROVIDER_URL,
    SSL_CONTEXT,
    URL,
)

SCOPE = ApplicationScope()
REGISTRIES = {
    "zk": RegistryConfig(address="zookeeper://zk:2181"),
    "nacos": RegistryConfig(address="nacos://n:8848", subscribe=False),
}


def _registry_with(config: DubboConfig) -> URL:
    registries = {"zk": RegistryConfig(address="zookeeper://zk:2181")}
    named = attrs.evolve(config, application=ApplicationConfig(name="users"), registries=registries)
    [registry] = service_registries(named, "Users", SCOPE)
    return registry


def _service(interface: str, *methods: str) -> Service:
    return Service(interface=interface, methods=[Method(name=name, request=(), response=None) for name in methods])


def test_a_service_takes_the_providers_settings_under_its_own():
    config = DubboConfig(
        application=ApplicationConfig(name="users"),
        registries=REGISTRIES,
        protocols={"tri": ProtocolConfig(name="tri", port=50051, triple=TripleConfig(compressor="gzip"))},
        provider=ProviderConfig(
            version="1.0",
            timeout=3,
            filters=("log",),
            registries=("zk",),
            services={"Users": ServiceConfig(group="beta", methods={"getUser": MethodConfig(timeout=10)})},
        ),
    )

    assert service_urls(config, _service("Users", "getUser", "rename"), SCOPE) == [
        URL(
            protocol="tri",
            host="0.0.0.0",
            port=50051,
            path="Users",
            parameters={
                "triple.compressor": "gzip",
                "application": "users",
                "group": "beta",
                "version": "1.0",
                "timeout": "3000",
                "service.filter": "log",
                "getUser.timeout": "10000",
            },
        ),
    ]
    registries = service_registries(config, "Users", SCOPE)
    assert registries == [URL.parse("zookeeper://zk:2181")]
    assert registries[0].attributes[APPLICATION_SCOPE] is SCOPE


def test_a_protocol_without_a_name_serves_the_protocol_its_key_names():
    config = DubboConfig(
        protocols={"tri": ProtocolConfig(port=50051), "public": ProtocolConfig(name="tri", port=50052)},
    )

    urls = [*service_urls(config, _service("Users"), SCOPE), *internal_service_urls(config, ["Users"], SCOPE).values()]

    assert [(url.protocol, url.port) for url in urls] == [("tri", 50051), ("tri", 50052), ("tri", 50051)]


def test_each_protocol_advertises_its_own_port_else_that_of_the_application():
    config = DubboConfig(
        application=ApplicationConfig(name="users", advertised_port=40000),
        protocols={
            "tri": ProtocolConfig(name="tri", advertised_port=30051),
            "dubbo": ProtocolConfig(name="dubbo"),
            "rest": ProtocolConfig(name="rest", advertised_port=8080),
        },
    )

    urls = [*service_urls(config, _service("Users"), SCOPE), *internal_service_urls(config, ["Users"], SCOPE).values()]

    assert [(url.protocol, url.attributes[ADVERTISED_PORT]) for url in urls] == [
        ("tri", 30051),
        ("dubbo", 40000),
        ("rest", 8080),
    ] * 2
    unset = DubboConfig(application=ApplicationConfig(name="users"))
    assert ADVERTISED_PORT not in service_urls(unset, _service("Users"), SCOPE)[0].attributes


def test_a_reference_takes_the_consumers_settings_and_its_subscribing_registries():
    config = DubboConfig(
        application=ApplicationConfig(name="orders", advertised_host="10.0.0.1"),
        registries=REGISTRIES,
        consumer=ConsumerConfig(
            retries=1, references={"Users": ReferenceConfig(check=False, methods={"rename": MethodConfig(retries=0)})}
        ),
    )

    url = reference_url(config, _service("Users", "getUser", "rename"), SCOPE)

    assert url == URL(
        protocol="consumer",
        host="10.0.0.1",
        path="Users",
        parameters={"application": "orders", "retries": "1", "check": "false", "rename.retries": "0"},
    )
    assert url.attributes[APPLICATION_SCOPE] is SCOPE
    assert direct_urls(config, url) == []
    assert reference_registries(config, "Users", SCOPE) == [URL.parse("zookeeper://zk:2181")]


def test_a_direct_reference_calls_its_urls_with_the_tags_they_are_written_with():
    reference = ReferenceConfig(urls=("tri://10.0.0.5:50051", "tri://10.0.0.6:50051?dubbo.tag=blue"), tag="gray")
    config = DubboConfig(consumer=ConsumerConfig(references={"Users": reference}))

    url = reference_url(config, _service("Users"), SCOPE)

    assert url.parameters["dubbo.tag"] == "gray"
    assert [direct.parameters.get("dubbo.tag") for direct in direct_urls(config, url)] == [None, "blue"]


def test_a_direct_reference_calls_its_urls_with_its_parameters_over_theirs():
    reference = ReferenceConfig(urls=("tri://10.0.0.5:50051?timeout=1&a=b",), timeout=2)
    config = DubboConfig(consumer=ConsumerConfig(references={"Users": reference}))

    url = reference_url(config, _service("Users"), SCOPE)

    [direct] = direct_urls(config, url)
    assert direct == URL.parse("tri://10.0.0.5:50051/Users?timeout=2000&a=b")
    assert direct.attributes[PROVIDER_URL] == URL.parse("tri://10.0.0.5:50051/Users?timeout=1&a=b")
    assert direct.scope is url.scope


def test_reference_triple_parameters_merge_key_by_key_over_the_consumers():
    reference = ReferenceConfig(urls=("tri://h:1",), triple=TripleConfig(parameters={"b": "reference", "c": "x"}))
    config = DubboConfig(
        consumer=ConsumerConfig(
            triple=TripleConfig(compressor="gzip", connect_timeout=1.5, parameters={"a": "consumer", "b": "consumer"}),
            references={"Users": reference},
        ),
    )

    parameters = reference_url(config, _service("Users"), SCOPE).parameters

    assert parameters == {
        "triple.a": "consumer",
        "triple.b": "reference",
        "triple.c": "x",
        "triple.compressor": "gzip",
        "triple.connect-timeout": "1500",
    }


def test_a_direct_reference_discovers_only_in_the_registries_it_selects_itself():
    registries = {"zk": RegistryConfig(address="zookeeper://zk:2181")}
    reference = ReferenceConfig(urls=("tri://h:1",))
    config = DubboConfig(
        application=ApplicationConfig(name="orders"),
        registries=registries,
        consumer=ConsumerConfig(registries=("zk",), references={"Users": reference}),
    )
    assert direct_urls(config, reference_url(config, _service("Users"), SCOPE)) == [
        URL.parse("tri://h:1/Users?application=orders")
    ]
    assert reference_registries(config, "Users", SCOPE) == []

    reference = ReferenceConfig(urls=("tri://h:1",), registries=("zk",))
    config = DubboConfig(
        application=ApplicationConfig(name="orders"),
        registries=registries,
        consumer=ConsumerConfig(references={"Users": reference}),
    )
    assert reference_registries(config, "Users", SCOPE) == [URL.parse("zookeeper://zk:2181")]


def test_internal_services_take_the_settings_of_the_protocols_of_the_services_but_not_of_the_provider():
    config = DubboConfig(
        application=ApplicationConfig(name="users"),
        protocols={
            "spare": ProtocolConfig(name="tri", port=50050),
            "tri": ProtocolConfig(name="tri", port=50051, triple=TripleConfig(compressor="gzip")),
            "other-tri": ProtocolConfig(name="tri", port=50052),
            "dubbo": ProtocolConfig(name="dubbo", port=20880, dubbo=DubboProtocolConfig(payload=1024)),
        },
        provider=ProviderConfig(timeout=3, filters=("log",), token=True, protocols=("tri", "other-tri", "dubbo")),
    )

    urls = internal_service_urls(config, ["Users"], SCOPE)

    assert urls == {
        "tri": URL(
            protocol="tri",
            host="0.0.0.0",
            port=50051,
            parameters={"triple.compressor": "gzip", "application": "users"},
        ),
        "dubbo": URL(
            protocol="dubbo", host="0.0.0.0", port=20880, parameters={"payload": "1024", "application": "users"}
        ),
    }
    assert urls["tri"].attributes == {APPLICATION_SCOPE: SCOPE}


def test_registries_name_the_metadata_report_set_apart_from_them():
    registries = {"zk": RegistryConfig(address="zookeeper://zk:2181")}
    config = DubboConfig(application=ApplicationConfig(name="orders"), registries=registries)
    assert METADATA_REPORT_URL not in service_registries(config, "Users", SCOPE)[0].attributes

    report = MetadataReportConfig(address="zookeeper://meta:2181", group="g", parameters={"timeout": "500"})
    config = DubboConfig(application=ApplicationConfig(name="orders"), registries=registries, metadata_report=report)
    [registry] = reference_registries(config, "Users", SCOPE)

    named = registry.attributes[METADATA_REPORT_URL]
    assert named == URL.parse("zookeeper://meta:2181?group=g&timeout=500")
    assert named.attributes[APPLICATION_SCOPE] is SCOPE


def test_a_reference_needs_urls_or_a_registry_it_subscribes_to():
    with pytest.raises(ConfigError, match="needs urls"):
        reference_registries(DubboConfig(), "Users", SCOPE)

    config = DubboConfig(application=ApplicationConfig(name="orders"), registries={"nacos": REGISTRIES["nacos"]})
    with pytest.raises(ConfigError, match="subscribes to none of its registries"):
        reference_registries(config, "Users", SCOPE)


def test_settings_reject_methods_the_service_does_not_have():
    config = DubboConfig(
        provider=ProviderConfig(services={"Users": ServiceConfig(methods={"get_user": MethodConfig(timeout=1)})}),
        consumer=ConsumerConfig(references={"Users": ReferenceConfig(methods={"nope": MethodConfig(timeout=1)})}),
    )

    with pytest.raises(ConfigError, match="service 'Users' configures methods it does not have: get_user"):
        service_urls(config, _service("Users", "getUser"), SCOPE)
    with pytest.raises(ConfigError, match="reference 'Users' configures methods it does not have: nope"):
        reference_url(config, _service("Users", "getUser"), SCOPE)


def test_triple_settings_stay_after_their_prefix_apart_from_the_service_identity():
    reference = ReferenceConfig(urls=("tri://h:1",), group="a", triple=TripleConfig(parameters={"group": "b"}))
    config = DubboConfig(consumer=ConsumerConfig(references={"Users": reference}))

    parameters = reference_url(config, _service("Users"), SCOPE).parameters

    assert (parameters["group"], parameters["triple.group"]) == ("a", "b")


def test_dubbo_protocol_settings_reach_the_service_urls():
    settings = DubboProtocolConfig(payload=1024, heartbeat=30, heartbeat_timeout=90, max_concurrent_calls=50)
    dubbo_protocol = ProtocolConfig(name="dubbo", dubbo=settings)
    config = DubboConfig(protocols={"d": dubbo_protocol})

    (served,) = service_urls(config, _service("Users"), SCOPE)

    assert {key: served.parameters[key] for key in ("payload", "heartbeat", "heartbeat.timeout")} == {
        "payload": "1024",
        "heartbeat": "30000",
        "heartbeat.timeout": "90000",
    }
    assert served.parameters["max-concurrent-calls"] == "50"


def test_the_shutdown_grace_reaches_both_sides_as_shutwait():
    config = DubboConfig(shutdown=ShutdownConfig(grace=2.5))

    (served,) = service_urls(config, _service("Users"), SCOPE)
    referred = reference_url(config, _service("Users"), SCOPE)

    assert served.parameters["shutwait"] == referred.parameters["shutwait"] == "2500"
    assert "shutwait" not in reference_url(DubboConfig(), _service("Users"), SCOPE).parameters


def test_tls_files_reach_both_sides_and_each_context_its_own():
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    client_context = ssl.create_default_context()
    tls = TLSConfig(certfile="c.pem", cafile="ca.pem", server_context=server_context, client_context=client_context)
    reference = ReferenceConfig(urls=("tri://10.0.0.5:50051",))
    config = DubboConfig(tls=tls, consumer=ConsumerConfig(references={"Users": reference}))
    files = {"ssl-enabled": "true", "tls-cert-file": "c.pem", "ca-cert-file": "ca.pem"}

    (served,) = service_urls(config, _service("Users"), SCOPE)
    referred = reference_url(config, _service("Users"), SCOPE)
    (direct,) = direct_urls(config, referred)

    assert files.items() <= served.parameters.items()
    assert served.attributes[SSL_CONTEXT] is server_context
    assert files.items() <= referred.parameters.items()
    assert referred.attributes[SSL_CONTEXT] is client_context
    assert direct.attributes[SSL_CONTEXT] is client_context
    internal = internal_service_urls(config, ["Users"], SCOPE)["tri"]
    assert files.items() <= internal.parameters.items()
    assert internal.attributes[SSL_CONTEXT] is server_context
    # The MetadataService of instances is called as the references call.
    metadata_consumer = _registry_with(config).attributes[METADATA_CONSUMER_URL]
    assert files.items() <= metadata_consumer.parameters.items()
    assert metadata_consumer.attributes[SSL_CONTEXT] is client_context
    assert "ssl-enabled" not in reference_url(DubboConfig(), _service("Users"), SCOPE).parameters


def test_a_token_of_true_is_one_random_token_for_all_protocols_and_one_of_false_none():
    protocols = {"a": ProtocolConfig(name="tri", port=1), "b": ProtocolConfig(name="tri", port=2)}
    services = {"Orders": ServiceConfig(token=False), "Items": ServiceConfig(token="s3")}
    config = DubboConfig(protocols=protocols, provider=ProviderConfig(token=True, services=services))

    first, second = (url.parameters["token"] for url in service_urls(config, _service("Users"), SCOPE))
    assert first == second
    assert len(first) == 32
    assert service_urls(config, _service("Users"), SCOPE)[0].parameters["token"] != first
    assert all("token" not in url.parameters for url in service_urls(config, _service("Orders"), SCOPE))
    assert service_urls(config, _service("Items"), SCOPE)[0].parameters["token"] == "s3"


def test_governance_settings_and_parameters_reach_the_urls_below_the_fields():
    method = MethodConfig(tps=2, deprecated=False, actives=1)
    service = ServiceConfig(
        executes=4, deprecated=True, serialization="json", parameters={"b": "service"}, methods={"getUser": method}
    )
    provider = ProviderConfig(accesslog=True, tps=10, tps_interval=1.5, parameters={"a": "provider", "b": "provider"})
    reference = ReferenceConfig(urls=("tri://h:1",), parameters={"d": "reference"}, methods={"getUser": method})
    config = DubboConfig(
        provider=attrs.evolve(provider, services={"Users": service}),
        consumer=ConsumerConfig(
            actives=3, serialization="json", parameters={"c": "consumer"}, references={"Users": reference}
        ),
    )

    (served,) = service_urls(config, _service("Users", "getUser"), SCOPE)
    referred = reference_url(config, _service("Users", "getUser"), SCOPE)

    assert {
        "accesslog": "true",
        "tps": "10",
        "tps.interval": "1500",
        "executes": "4",
        "deprecated": "true",
        "getUser.tps": "2",
        "getUser.deprecated": "false",
        "serialization": "json",
        "a": "provider",
        "b": "service",
    }.items() <= served.parameters.items()
    assert {
        "actives": "3",
        "getUser.actives": "1",
        "serialization": "json",
        "c": "consumer",
        "d": "reference",
    }.items() <= referred.parameters.items()
    with pytest.raises(ValueError, match="set the timeout field instead of the 'timeout' parameter"):
        ServiceConfig(parameters={"timeout": "1"})


def test_a_reference_leaves_out_the_settings_of_methods_that_only_providers_read():
    method = MethodConfig(retries=1, loadbalance="first", weight=5, deprecated=True, tps=1)
    reference = ReferenceConfig(urls=("tri://h:1",), methods={"getUser": method})
    service = ServiceConfig(methods={"getUser": method})
    config = DubboConfig(
        provider=ProviderConfig(services={"Users": service}), consumer=ConsumerConfig(references={"Users": reference})
    )

    (served,) = service_urls(config, _service("Users", "getUser"), SCOPE)
    referred = reference_url(config, _service("Users", "getUser"), SCOPE)

    assert {
        "getUser.weight": "5",
        "getUser.deprecated": "true",
        "getUser.tps": "1",
    }.items() <= served.parameters.items()
    assert {key for key in referred.parameters if key.startswith("getUser.")} == {
        "getUser.retries",
        "getUser.loadbalance",
    }
