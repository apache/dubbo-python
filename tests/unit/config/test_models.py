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

from pathlib import Path

import attrs
import pytest

from dubbo.config import (
    ApplicationConfig,
    ConfigCenterConfig,
    DubboConfig,
    MetadataReportConfig,
    ProtocolConfig,
    ProviderConfig,
    RegistryConfig,
    ServiceConfig,
    TLSConfig,
    TripleConfig,
)
from dubbo.config.fields import to_url_parameters


def test_code_construction_validates_without_loading():
    config = DubboConfig(
        application=ApplicationConfig(name="orders"),
        # Port conflicts are left to the server that binds them.
        protocols={"tri": ProtocolConfig(name="tri", port=50051), "dubbo": ProtocolConfig(name="dubbo", port=50051)},
        provider=ProviderConfig(protocols=("tri",)),
    )
    assert config.provider.protocols == ("tri",)
    with pytest.raises(ValueError, match="undefined registry"):
        DubboConfig(application=ApplicationConfig(name="orders"), provider=ProviderConfig(registries=("default",)))
    with pytest.raises(TypeError, match="'registries' must be <class 'tuple'>"):
        ProviderConfig(registries="default")


@pytest.mark.parametrize("model", [RegistryConfig, ConfigCenterConfig])
@pytest.mark.parametrize(
    ("address", "message"),
    [
        ("localhost:2181", "needs a scheme"),
        ("zookeeper:///root", "needs a host"),
        ("zookeeper://zk1:2181,,zk2:2181", "empty host"),
        ("zookeeper://", "needs a host"),
        ("zookeeper://zk1:2181,", "empty host"),
        ("zookeeper://zk1:2181,zk2:2181?backup=zk3:2181", "both after commas and in 'backup'"),
    ],
)
def test_addresses_need_a_scheme_and_hosts(model, address, message):
    with pytest.raises(ValueError, match=f"address .*{message}"):
        model(address=address)


@pytest.mark.parametrize("model", [RegistryConfig, ConfigCenterConfig])
def test_rejected_address_does_not_echo_its_password(model):
    with pytest.raises(ValueError, match="fragments") as caught:
        model(address="zookeeper://alice:hunter2@localhost:2181/#fragment")

    assert "hunter2" not in str(caught.value)


def test_registry_url_moves_further_hosts_to_backup_and_adds_parameters():
    url = RegistryConfig(address="zookeeper://zk1:2181,zk2:2181/dubbo", parameters={"session": "60000"}).to_url()

    assert (url.protocol, url.host, url.port, url.path) == ("zookeeper", "zk1", 2181, "dubbo")
    assert url.parameters == {"backup": "zk2:2181", "session": "60000"}


def test_config_center_url_adds_fields_with_defaults_and_parameters():
    config = ConfigCenterConfig(
        address="nacos://user:secret@n1:8848?cluster=east", namespace="dev", parameters={"region": "cn"}
    )

    url = config.to_url()

    assert (url.username, url.password, url.host) == ("user", "secret", "n1")
    assert url.parameters == {"cluster": "east", "namespace": "dev", "timeout": "30000", "region": "cn"}
    assert attrs.evolve(config, timeout=0.0001).to_url().parameters["timeout"] == "1"


@pytest.mark.parametrize("model", [RegistryConfig, ConfigCenterConfig])
def test_parameters_are_strings_that_do_not_collide_with_the_address(model):
    with pytest.raises(TypeError, match="must be <class 'str'>"):
        model(address="nacos://n:8848", parameters={"retries": 3})
    with pytest.raises(ValueError, match="'cluster' differs from the one in the address"):
        model(address="nacos://n:8848?cluster=a", parameters={"cluster": "b"})
    with pytest.raises(ValueError, match="'backup' differs from the one in the address"):
        model(address="nacos://n1:8848,n2:8848", parameters={"backup": "n3:8848"})


def test_triple_parameters_are_strings_that_fields_do_not_set():
    with pytest.raises(TypeError, match="must be <class 'str'>"):
        TripleConfig(parameters={"stream-send-buffer-size": 1048576})
    with pytest.raises(ValueError, match="set the compressor field instead of the 'compressor' parameter"):
        TripleConfig(parameters={"compressor": "gzip"})


@pytest.mark.parametrize("field", ["namespace", "timeout"])
@pytest.mark.parametrize("place", ["address", "parameters"])
def test_a_config_center_option_comes_from_its_field_or_the_url_which_agree(field, place):
    fields = (
        {"address": f"nacos://n:8848?{field}=1"}
        if place == "address"
        else {"address": "nacos://n:8848", "parameters": {field: "1"}}
    )

    # Above all, the address and parameters override the default timeout.
    assert ConfigCenterConfig(**fields).to_url().parameters[field] == "1"
    # The field agrees once it becomes a URL parameter: a timeout of 0.001 seconds is 1 millisecond.
    same = {"namespace": "1", "timeout": 0.001}[field]
    assert ConfigCenterConfig(**fields, **{field: same}).to_url().parameters[field] == "1"
    with pytest.raises(ValueError, match=f"the {field} field and the '{field}' parameter differ"):
        ConfigCenterConfig(**fields, **{field: 2})


@pytest.mark.parametrize("model", [RegistryConfig, MetadataReportConfig])
def test_a_namespace_comes_from_its_field_or_the_url_which_agree(model):
    for fields in (
        {"address": "nacos://n:8848", "namespace": "dev"},
        {"address": "nacos://n:8848?namespace=dev"},
        {"address": "nacos://n:8848", "parameters": {"namespace": "dev"}},
    ):
        assert model(**fields).to_url().parameters == {"namespace": "dev"}
    # One value set twice is set once.
    assert model(address="nacos://n:8848?namespace=dev", namespace="dev").to_url().parameters == {"namespace": "dev"}
    with pytest.raises(ValueError, match="the namespace field and the 'namespace' parameter differ"):
        model(address="nacos://n:8848?namespace=dev", namespace="prod")


@pytest.mark.parametrize(
    ("registry", "expected"),
    [
        ({"group": "orders", "namespace": "dev"}, "dev"),
        ({"address": "nacos://n:8848?namespace=dev", "group": "orders"}, "dev"),
        ({"parameters": {"namespace": "dev"}}, "dev"),
        ({"group": "orders"}, "orders"),
        ({"address": "nacos://n:8848?group=orders"}, "orders"),
        ({"address": "nacos://n:8848?group=orders&namespace=dev", "group": "orders", "namespace": "dev"}, "dev"),
    ],
)
def test_the_config_center_of_a_registry_is_in_its_namespace_else_its_group(registry, expected):
    center = ConfigCenterConfig.from_registry(RegistryConfig(**{"address": "nacos://n:8848", **registry}))

    assert (center.namespace, center.parameters) == (expected, {})


def test_a_registry_address_keeps_credentials_path_and_query_on_the_first_host():
    url = RegistryConfig(address=" zookeeper://user:secret@zk1:2181,[::1]:2181/root?session=5 ").to_url()

    assert (url.username, url.password, url.host, url.port, url.path) == ("user", "secret", "zk1", 2181, "root")
    assert url.parameters == {"session": "5", "backup": "[::1]:2181"}


def test_a_registry_group_and_a_service_warmup_become_url_parameters():
    assert RegistryConfig(address="zookeeper://zk:2181", group="orders").to_url().parameters == {"group": "orders"}
    assert RegistryConfig(address="zookeeper://zk:2181?group=orders").to_url().parameters == {"group": "orders"}
    assert to_url_parameters(ServiceConfig(warmup=60)) == {"warmup": "60000"}


def test_the_advertised_port_of_the_application_goes_to_one_protocol_at_most():
    def config(**ports: int | None) -> DubboConfig:
        protocols = {name: ProtocolConfig(name=name, advertised_port=port) for name, port in ports.items()}
        return DubboConfig(application=ApplicationConfig(advertised_port=40000), protocols=protocols)

    config(tri=None)
    config(tri=None, dubbo=30880)
    with pytest.raises(ValueError, match="for the protocols 'tri', 'dubbo'; set advertised_port on each of them"):
        config(tri=None, dubbo=None)


def test_tls_files_may_be_paths_and_are_kept_as_text():
    cert, key, ca = Path("certs/server.pem"), Path("certs/server.key"), Path("certs/ca.pem")
    tls = TLSConfig(certfile=cert, keyfile=key, cafile=ca)

    assert (tls.certfile, tls.keyfile, tls.cafile) == (str(cert), str(key), str(ca))
    assert to_url_parameters(tls)["tls-cert-file"] == str(cert)
