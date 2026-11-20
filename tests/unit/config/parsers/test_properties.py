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

from dubbo.config import ConfigParseError, ConfigParser, DubboConfig
from dubbo.config.structure import structure_config
from dubbo.extension import Extensions


def test_properties_nests_dotted_keys_and_keeps_strings_and_java_escapes():
    pytest.importorskip("dotproperties")
    parser = Extensions().get(ConfigParser, "properties")()
    assert parser.loads(
        "application.name=orders\nprotocols.tri.port=1\nprotocols.tri.port=50051\napplication.version=\\u4F60\\u597D\n"
    ) == {
        "application": {"name": "orders", "version": "你好"},
        "protocols": {"tri": {"port": "50051"}},
    }


def test_properties_reports_an_invalid_java_escape():
    pytest.importorskip("dotproperties")
    parser = Extensions().get(ConfigParser, "properties")()

    with pytest.raises(ConfigParseError, match="invalid properties configuration") as caught:
        parser.loads("bad=\\uXYZZ")
    assert isinstance(caught.value.__cause__, ValueError)


@pytest.mark.parametrize("text", ["a=1\na.b=2", "a.b=2\na=1", "a..b=1", ".a=1", "a.=1"])
def test_properties_rejects_conflicting_or_empty_key_segments(text):
    pytest.importorskip("dotproperties")
    with pytest.raises(ConfigParseError, match="invalid properties key"):
        Extensions().get(ConfigParser, "properties")().loads(text)


def test_properties_keeps_the_dots_of_a_bracketed_segment_so_a_service_is_named_whole():
    pytest.importorskip("dotproperties")
    parser = Extensions().get(ConfigParser, "properties")()

    data = parser.loads(
        "provider.services[com.example.Greeter].timeout=3000\n"
        "provider.services.[com.example.Greeter].methods.greet.retries=1\n"
    )
    config = structure_config(data, DubboConfig)

    assert data == {
        "provider": {"services": {"com.example.Greeter": {"timeout": "3000", "methods": {"greet": {"retries": "1"}}}}}
    }
    greeter = config.provider.services["com.example.Greeter"]
    assert (greeter.timeout, greeter.methods["greet"].retries) == (3000, 1)


@pytest.mark.parametrize("key", ["a[b", "a[]", "a]b", "a[b]c", "a.[b"])
def test_properties_rejects_an_unclosed_or_empty_bracket(key):
    pytest.importorskip("dotproperties")
    with pytest.raises(ConfigParseError, match="invalid properties key"):
        Extensions().get(ConfigParser, "properties")().loads(f"{key}=1")


def test_properties_reads_json_where_the_configuration_expects_a_list():
    pytest.importorskip("dotproperties")
    parser = Extensions().get(ConfigParser, "properties")()

    data = parser.loads(
        'consumer.references[com.example.Echo].urls=["tri://127.0.0.1:50051"]\napplication.name=["a"]\n'
    )

    assert data == {
        "consumer": {"references": {"com.example.Echo": {"urls": ["tri://127.0.0.1:50051"]}}},
        "application": {"name": '["a"]'},
    }
    with pytest.raises(ConfigParseError, match=r"'consumer\.references\.com\.example\.Echo\.urls' must be JSON"):
        parser.loads("consumer.references[com.example.Echo].urls=tri://127.0.0.1:50051")
