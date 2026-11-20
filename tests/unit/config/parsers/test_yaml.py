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

from dubbo.config import ConfigParseError, ConfigParser
from dubbo.extension import Extensions


def test_yaml_reads_a_mapping():
    pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()

    assert parser.loads("application:\n  name: orders\n") == {"application": {"name": "orders"}}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("!!python/object/apply:builtins.str [123]", "invalid YAML configuration"),
        ("1: value", "configuration keys must be strings, in the mapping at line 1"),
        ("consumer:\n  1: value", "configuration keys must be strings, in the mapping at line 2"),
        ("- item", "configuration must have a mapping at its root"),
    ],
    ids=["python-object", "non-string-key", "nested-non-string-key", "non-mapping-root"],
)
def test_yaml_rejects_content_outside_the_configuration_format(text, message):
    pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()

    with pytest.raises(ConfigParseError, match=message):
        parser.loads(text)


@pytest.mark.parametrize(
    "text",
    ["root: &r {child: *r}", "&r {child: *r}", "root: &r [*r]", "a: &a {child: &b {child: *a}}"],
)
def test_yaml_rejects_recursive_aliases_at_the_parser(text):
    yaml = pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()
    with pytest.raises(ConfigParseError, match="invalid YAML configuration") as caught:
        parser.loads(text)
    assert isinstance(caught.value.__cause__, yaml.YAMLError)


def test_yaml_accepts_shared_aliases_and_merge_keys():
    pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()
    data = parser.loads("base: &b {timeout: 10}\ncopy: *b\nmerged: {<<: *b, retries: 2}")
    assert data == {
        "base": {"timeout": 10},
        "copy": {"timeout": 10},
        "merged": {"timeout": 10, "retries": 2},
    }


def test_yaml_counts_only_what_aliases_add_against_the_node_budget():
    pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()
    services = {f"s{i}": {"timeout": 1, "weight": 2} for i in range(2000)}

    assert parser.loads("\n".join(f"{name}: {{timeout: 1, weight: 2}}" for name in services)) == services


def test_yaml_rejects_aliases_that_expand_past_the_node_budget():
    pytest.importorskip("yaml")
    parser = Extensions().get(ConfigParser, "yaml")()
    lines = ["a0: &a0 {x: 1, y: 1}"]
    lines += [f"a{i}: &a{i} {{x: *a{i - 1}, y: *a{i - 1}}}" for i in range(1, 17)]

    with pytest.raises(ConfigParseError, match="aliases add more than"):
        parser.loads("\n".join(lines))
