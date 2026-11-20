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

import pytest

from dubbo.config import (
    ConfigError,
    DubboConfig,
    RegistryConfig,
)
from dubbo.config.structure import structure_config

APP = {"application": {"name": "orders"}}


@pytest.mark.parametrize(
    ("value", "message"),
    [("127.0.0.1:50051", "needs a scheme"), ("tri:///path", "needs a host")],
)
def test_an_invalid_reference_url_fails_to_configure(value, message):
    with pytest.raises(ConfigError, match=message):
        structure_config(
            {**APP, "consumer": {"references": {"com.example.UserService": {"urls": [value]}}}}, DubboConfig
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("true", True), (" Yes ", True), ("ON", True), ("1", True), ("off", False)],
)
def test_booleans_accept_real_booleans_and_standard_spellings(value, expected):
    config = structure_config({**APP, "consumer": {"check": value}}, DubboConfig)
    assert config.consumer.check is expected


@pytest.mark.parametrize("value", ["maybe", "", "enabled", 1, 0])
def test_booleans_reject_other_values(value):
    with pytest.raises(ConfigError, match=r"expected a boolean.* @ config\.consumer\.check"):
        structure_config({**APP, "consumer": {"check": value}}, DubboConfig)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"registries": {"zk": {"address": "zookeeper://h:1", "use_as_config_center": False}}},
            r"application\.name is required once a registry is defined",
        ),
        ({"application": {"name": "orders", "nmae": "x"}}, r"extra fields found \(nmae\) @ config\.application"),
        (
            {**APP, "protocols": {"tri": {"name": "tri", "port": True}}},
            r"integer, got True @ config\.protocols\['tri'\]",
        ),
        ({**APP, "protocols": {"tri": {"name": "tri", "port": "8O"}}}, r"integer, got '8O'"),
        ({**APP, "protocols": {"tri": {"name": "tri", "port": 70000}}}, r"'port' must be <= 65535"),
        ({"application": {"name": 1}}, r"string, got 1 @ config\.application\.name"),
        ({**APP, "consumer": {"timeout": 0}}, r"'timeout' must be > 0"),
        ({**APP, "provider": {"registries": "default"}}, r"list of names, got 'default'"),
        ({**APP, "provider": {"protocols": ["dubbo"]}}, r"provider selects undefined protocol 'dubbo'"),
        (
            {**APP, "consumer": {"references": {"org.example.Users": {"registries": ["nope"]}}}},
            r"reference 'org\.example\.Users' selects undefined registry 'nope'",
        ),
    ],
)
def test_invalid_configuration_names_the_problem_and_path(data, message):
    with pytest.raises(ConfigError, match=message):
        structure_config(data, DubboConfig)


def test_invalid_configuration_lists_each_problem_on_a_line_without_the_errors_of_cattrs():
    with pytest.raises(ConfigError) as caught:
        structure_config({**APP, "protocols": {"tri": {"name": "tri", "port": "abc", "hots": 1}}}, DubboConfig)

    assert str(caught.value) == (
        "invalid configuration:\n"
        "  expected an integer, got 'abc' @ config.protocols['tri'].port\n"
        "  extra fields found (hots) @ config.protocols['tri']"
    )
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"zk": {"address": "zookeeper://h:1", "weight": "oops"}}, r"integer, got 'oops' @ config\.registries\['zk'\]"),
        (["zookeeper://h:1"], r"expected a mapping, got list @ config\.registries"),
    ],
    ids=["invalid-entry", "not-a-mapping"],
)
def test_a_section_structured_alone_names_the_problem_and_path(data, message):
    with pytest.raises(ConfigError, match=message):
        structure_config(data, dict[str, RegistryConfig], path="config.registries")
