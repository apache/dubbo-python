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

import sys

import pytest

from dubbo import Dubbo
from dubbo.config import (
    ApplicationConfig,
    ConfigCenterConfig,
    ConfigError,
    ConfigParseError,
    ConfigParser,
    ConfigReadError,
    ConsumerConfig,
    ProviderConfig,
    RegistryConfig,
    ServiceConfig,
    TripleConfig,
)
from dubbo.config.loading import load_config
from dubbo.config.structure import unstructure_config
from dubbo.extension import ApplicationScope, extensions

APP = {"application": {"name": "orders"}}
pytestmark = pytest.mark.anyio


@pytest.fixture
async def layered(tmp_path, monkeypatch):
    path = tmp_path / "dubbo.json"
    path.write_text(
        '{"application": {"name": "orders", "version": "1"},'
        ' "registries": {"default": {"address": "zookeeper://zk:2181", "use_as_config_center": false}},'
        ' "consumer": {"timeout": 3, "retries": 2, "registries": ["default"]}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("LAYER_TEST__CONSUMER__TIMEOUT", "1.5")
    monkeypatch.setenv("LAYER_TEST__CONSUMER__REGISTRIES", "[]")

    return await _configure(
        path,
        {"application": {"version": "2"}},
        env_prefix="LAYER_TEST__",
        consumer=ConsumerConfig(retries=5),
    )


async def test_a_later_source_overrides_only_the_fields_it_sets(layered):
    assert layered.application == ApplicationConfig(name="orders", version="2")
    assert layered.registries == {"default": RegistryConfig(address="zookeeper://zk:2181", use_as_config_center=False)}


async def test_environment_variables_override_the_sources_with_converted_values(layered):
    assert (layered.consumer.timeout, layered.consumer.registries) == (1.5, ())


async def test_code_overrides_the_sources(layered):
    assert layered.consumer.retries == 5


async def test_keyword_objects_keep_lower_values_for_unset_fields():
    source = {
        **APP,
        "registries": {"default": {"address": "zookeeper://zk:2181", "use_as_config_center": False}},
        "provider": {"group": "blue", "services": {"org.example.Users": {"timeout": 2}}},
    }
    config = await _configure(
        source,
        registries={"backup": RegistryConfig(address="nacos://n:8848", use_as_config_center=False)},
        provider=ProviderConfig(timeout=3),
    )
    assert set(config.registries) == {"default", "backup"}
    assert config.provider == ProviderConfig(
        group="blue", timeout=3, services={"org.example.Users": ServiceConfig(timeout=2)}
    )


async def test_triple_settings_nest_in_files_and_environment_variables(monkeypatch):
    monkeypatch.setenv("NEST_TEST__CONSUMER__TRIPLE__COMPRESSOR", "gzip")
    config = await _configure(
        APP,
        {"protocols": {"tri": {"name": "tri", "triple": {"health_enabled": "true", "keep_alive_interval": 30}}}},
        env_prefix="NEST_TEST__",
    )

    assert config.protocols["tri"].triple == TripleConfig(health_enabled=True, keep_alive_interval=30.0)
    assert config.consumer.triple == TripleConfig(compressor="gzip")


async def test_files_select_parsers_by_suffix(tmp_path):
    pytest.importorskip("yaml")
    pytest.importorskip("dotproperties")
    yaml_path = tmp_path / "dubbo.yml"
    yaml_path.write_text("application:\n  name: orders\n", encoding="utf-8")
    properties_path = tmp_path / "dubbo.properties"
    properties_path.write_text("consumer.check=off\n", encoding="utf-8")

    config = await _configure(str(yaml_path), properties_path)
    assert (config.application.name, config.consumer.check) == ("orders", False)


async def test_files_use_parsers_registered_on_the_shared_extensions(tmp_path, isolated_extensions):
    class UpperParser:
        def loads(self, text):
            return {"application": {"name": text.strip().upper()}}

    extensions.register(ConfigParser, "upper", UpperParser)
    path = tmp_path / "dubbo.upper"
    path.write_text("orders", encoding="utf-8")
    assert (await _configure(path)).application.name == "ORDERS"


async def test_a_file_whose_suffix_names_no_installed_parser_cannot_be_read(tmp_path):
    unknown = tmp_path / "dubbo.ini"
    unknown.write_text("", encoding="utf-8")

    with pytest.raises(ConfigReadError, match="parser 'ini'"):
        await _configure(unknown)


async def test_a_file_without_a_suffix_cannot_be_read(tmp_path):
    with pytest.raises(ConfigReadError, match="has no suffix"):
        await _configure(tmp_path / "dubbo")


async def test_a_file_invalid_in_its_format_cannot_be_parsed(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    with pytest.raises(ConfigParseError, match=r"invalid JSON configuration in '.*broken\.json'"):
        await _configure(broken)


async def test_env_nests_paths_and_converts_scalar_fields(monkeypatch):
    monkeypatch.setenv("ENV_TEST__APPLICATION__NAME", "orders")
    monkeypatch.setenv("ENV_TEST__PROTOCOLS__TRI__PORT", "50051")

    config = await _configure(env_prefix="ENV_TEST__")

    assert config.protocols["tri"].port == 50051


async def test_env_keeps_a_text_field_as_text_even_when_it_reads_as_json(monkeypatch):
    monkeypatch.setenv("ENV_TEST__APPLICATION__NAME", '["kept as text"]')

    config = await _configure(env_prefix="ENV_TEST__")

    assert config.application.name == '["kept as text"]'


async def test_env_decodes_json_for_structured_fields(monkeypatch):
    monkeypatch.setenv("JSON_TEST__APPLICATION__NAME", "orders")
    monkeypatch.setenv("JSON_TEST__CONSUMER__REFERENCES", '{"org.example.UserService": {"timeout": 1.0}}')
    monkeypatch.setenv("JSON_TEST__PROVIDER__REGISTRIES", '["default"]')
    monkeypatch.setenv("JSON_TEST__REGISTRIES__DEFAULT", '{"address": "etcd://n:2379"}')

    config = await _configure(env_prefix="JSON_TEST__")

    assert config.consumer.references["org.example.UserService"].timeout == 1.0
    assert config.provider.registries == ("default",)
    assert config.registries["default"].address == "etcd://n:2379"


async def test_env_leaves_unknown_keys_undecoded_for_validation_to_reject(monkeypatch):
    monkeypatch.setenv("JSON_TEST__APPLICATION__NAME", "orders")
    monkeypatch.setenv("JSON_TEST__UNKNOWN", "{not json}")

    with pytest.raises(ConfigError, match=r"extra fields found \(unknown\)"):
        await _configure(env_prefix="JSON_TEST__")


async def test_env_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("BAD_JSON__CONSUMER__REFERENCES", "users")
    with pytest.raises(ConfigReadError, match=r"'consumer\.references' must be JSON"):
        await _configure(APP, env_prefix="BAD_JSON__")


@pytest.mark.parametrize(
    "variables",
    [
        {"ROOT": "scalar", "ROOT__CHILD": "value"},
        {"ROOT__CHILD": "value", "ROOT": "scalar"},
        {"ROOT____CHILD": "value"},
        pytest.param(
            {"ROOT": "upper", "root": "lower"},
            marks=pytest.mark.skipif(sys.platform == "win32", reason="Windows names variables regardless of case"),
        ),
        # A JSON value cannot be combined with variables inside it.
        {"CONSUMER__REFERENCES": "{}", "CONSUMER__REFERENCES__USERS__TIMEOUT": "1"},
    ],
)
async def test_env_rejects_ambiguous_paths(monkeypatch, variables):
    for key, value in variables.items():
        monkeypatch.setenv("PATH_TEST__" + key, value)
    with pytest.raises(ConfigReadError, match="invalid configuration path in environment variable"):
        await _configure(APP, env_prefix="PATH_TEST__")


async def test_the_address_to_register_comes_from_the_shared_environment_variables(monkeypatch):
    monkeypatch.setenv("DUBBO_IP_TO_REGISTRY", "10.0.0.1")
    monkeypatch.setenv("DUBBO_PORT_TO_REGISTRY", "20880")

    config = await _configure(APP, env_prefix="DUBBO_UNSET_TEST__")

    assert (config.application.advertised_host, config.application.advertised_port) == ("10.0.0.1", 20880)


async def test_the_advertised_port_of_a_protocol_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PORT_TEST__PROTOCOLS__TRI__ADVERTISED_PORT", "30051")

    config = await _configure({**APP, "protocols": {"tri": {"name": "tri"}}}, env_prefix="PORT_TEST__")

    assert config.protocols["tri"].advertised_port == 30051


CENTER = {"application": {"name": "orders"}, "config_center": {"address": "memory://center"}}
ENTRY = ("dubbo", "dubbo.yaml")


async def test_remote_configuration_ranks_between_sources_and_environment(config_store, monkeypatch):
    config_store.entries[ENTRY] = "consumer: {timeout: 2, group: remote, version: remote}"
    monkeypatch.setenv("CENTER_TEST__CONSUMER__GROUP", "env")

    config = await _configure(
        CENTER,
        {"consumer": {"timeout": 1, "check": False}},
        env_prefix="CENTER_TEST__",
        consumer=ConsumerConfig(version="code"),
    )

    consumer = config.consumer
    assert (consumer.timeout, consumer.check) == (2, False)
    assert (consumer.group, consumer.version) == ("env", "code")
    assert config_store.reads == [ENTRY]


async def test_remote_configuration_completes_the_local_configuration(config_store):
    config_store.entries[ENTRY] = "application: {name: orders}\nregistries: {zk: {address: 'zookeeper://zk:2181'}}"

    config = await _configure({"config_center": {"address": "memory://center"}, "provider": {"registries": ["zk"]}})

    assert config.application.name == "orders"
    assert config.registries == {"zk": RegistryConfig(address="zookeeper://zk:2181")}


async def test_config_center_merges_from_every_local_layer(config_store, monkeypatch):
    monkeypatch.setenv("CENTER_TEST__CONFIG_CENTER__TIMEOUT", "5")
    monkeypatch.setenv("CENTER_TEST__CONFIG_CENTER__NAMESPACE", "prod")
    source = {
        **CENTER,
        "config_center": {
            "address": "memory://file",
            "group": "shared",
            "namespace": "dev",
            "parameters": {"cluster": "east"},
        },
    }

    config = await _configure(
        source, env_prefix="CENTER_TEST__", config_center=ConfigCenterConfig(address="memory://code")
    )

    assert config.config_center == ConfigCenterConfig(
        address="memory://code", namespace="prod", group="shared", timeout=5, parameters={"cluster": "east"}
    )
    assert config_store.reads == [("shared", "dubbo.yaml")]


async def test_implementation_receives_the_url_with_the_application_scope(config_store):
    center = {
        "address": "memory://user:secret@center:2181,other:2181",
        "namespace": "dev",
        "timeout": 3,
        "parameters": {"session-timeout": 3000, "sasl": True},
    }

    async with Dubbo(CENTER, {"config_center": center}, env_prefix=None):
        (created,) = config_store.centers
        assert isinstance(created.url.scope, ApplicationScope)

    url = created.url
    assert (url.protocol, url.host, url.port, url.username, url.password) == (
        "memory",
        "center",
        2181,
        "user",
        "secret",
    )
    assert url.parameters == {
        "backup": "other:2181",
        "timeout": "3000",
        "namespace": "dev",
        "session-timeout": "3000",
        "sasl": "true",
    }


async def test_format_follows_the_key_suffix_unless_set(config_store):
    config_store.entries[("dubbo", "dubbo.properties")] = "consumer.retries = 4"
    config_store.entries[("dubbo", "settings")] = '{"consumer": {"retries": 5}}'
    center = {"address": "memory://center"}

    by_suffix = await _configure(CENTER, {"config_center": {**center, "config_file": "dubbo.properties"}})
    by_format = await _configure(CENTER, {"config_center": {**center, "config_file": "settings", "format": "json"}})

    assert (by_suffix.consumer.retries, by_format.consumer.retries) == (4, 5)


@pytest.mark.parametrize("text", [None, "  \n"])
async def test_missing_or_blank_entry_adds_nothing(config_store, text):
    if text is not None:
        config_store.entries[ENTRY] = text

    config = await _configure(CENTER, {"consumer": {"retries": 1}})

    assert config.consumer.retries == 1


async def test_an_entry_invalid_in_its_format_cannot_be_parsed(config_store):
    config_store.entries[ENTRY] = "consumer: ["

    with pytest.raises(ConfigParseError, match=r"invalid YAML configuration in 'dubbo\.yaml' of group 'dubbo'"):
        await _configure(CENTER)


async def test_connection_closes_when_startup_fails_after_connecting(config_store):
    config_store.entries[ENTRY] = "consumer: {retries: -1}"

    with pytest.raises(ConfigError, match="'retries' must be >= 0"):
        await _configure(CENTER)

    assert config_store.centers[0].closed


async def test_remote_configuration_cannot_set_the_configuration_center(config_store):
    config_store.entries[ENTRY] = "config_center: {address: 'memory://other'}"

    with pytest.raises(ConfigError, match="must not set config_center"):
        await _configure(CENTER)


@pytest.mark.parametrize(
    ("center", "error", "message"),
    [
        ({"address": "center:8848"}, ConfigError, "needs a scheme"),
        ({"address": "memory://center", "adress": "typo"}, ConfigError, "adress"),
        ({"address": "memory://center?timeout=1", "timeout": 2}, ConfigError, "timeout field and the 'timeout'"),
        ({"address": "memory://center?zone=a", "parameters": {"zone": "b"}}, ConfigError, "'zone' differs"),
        ({"address": "etcd://center:2379"}, ConfigReadError, "configuration center 'etcd'"),
        ({"address": "etcd://center:2379", "check": False}, ConfigReadError, "configuration center 'etcd'"),
    ],
)
async def test_invalid_configuration_center_fails_before_connecting(config_store, center, error, message):
    # The invalid consumer shows that the configuration center is checked first.
    with pytest.raises(error, match=message):
        await _configure(CENTER, {"config_center": center}, {"consumer": {"retries": -1}})

    assert config_store.centers == []


@pytest.mark.parametrize(
    ("center", "message"),
    [
        ({"address": "memory://center", "config_file": "settings"}, "no suffix and no format is set"),
        ({"address": "memory://center", "format": "ini"}, "parser 'ini'"),
    ],
)
async def test_missing_parser_fails_before_connecting_even_when_unchecked(config_store, center, message):
    with pytest.raises(ConfigReadError, match=message):
        await _configure(CENTER, {"config_center": {**center, "check": False}})

    assert config_store.centers == []


async def test_unreadable_center_fails_startup_by_default(config_store):
    config_store.error = ConnectionRefusedError("refused")

    with pytest.raises(ConfigReadError, match=r"memory://center\?timeout=30000") as caught:
        await _configure(CENTER)

    assert isinstance(caught.value.__cause__, ConnectionRefusedError)
    assert config_store.centers[0].closed


async def test_without_a_config_center_the_first_registry_of_a_kind_that_can_serve_as_one_does(config_store):
    config_store.entries[ENTRY] = "consumer: {timeout: 2}"
    registries = {
        "etcd": {"address": "etcd://n:2379"},
        "off": {"address": "memory://off", "use_as_config_center": False},
        "memory": {
            "address": "memory://u:p@a:1,b:2?timeout=1500&session=60000",
            "group": "prod",
            "parameters": {"x": "y"},
        },
    }

    config = await _configure({"application": {"name": "orders"}, "registries": registries})

    assert config.config_center == ConfigCenterConfig(
        address="memory://u:p@a:1",
        namespace="prod",
        timeout=1.5,
        parameters={"backup": "b:2", "session": "60000", "x": "y"},
    )
    assert (config.consumer.timeout, config_store.reads) == (2, [ENTRY])
    assert config.registries["memory"].use_as_config_center is None


async def test_registries_serve_as_no_config_center_when_one_is_set_or_none_can(config_store):
    config_store.entries[ENTRY] = "consumer: {timeout: 2}"
    registries = {"memory": {"address": "memory://registry"}}

    config = await _configure({**CENTER, "registries": registries})
    assert config.config_center == ConfigCenterConfig(address="memory://center")

    config = await _configure({"application": {"name": "orders"}, "registries": {"etcd": {"address": "etcd://n:2379"}}})
    assert config.config_center is None


async def _configure(*sources, env_prefix=None, **options):
    async with ApplicationScope() as scope:
        return await load_config(sources, env_prefix=env_prefix, code=unstructure_config(options), scope=scope)
