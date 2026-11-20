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

from dubbo.transport.nacos.sdk.connection import client_config
from dubbo.url import URL


@pytest.fixture
def config():
    return client_config(
        URL.parse("nacos://u:p@n1?backup=n2:9000,[::1],n3&namespace=dev&timeout=1500&accessKey=ak&secretKey=sk")
    )


def test_sdk_settings_name_each_server_with_its_port(config):
    assert config.server_list == ["n1:8848", "n2:9000", "[::1]:8848", "n3:8848"]


def test_sdk_settings_bracket_an_ipv6_server_that_names_no_port():
    config = client_config(URL.parse("nacos://[::1]?backup=::2"))

    assert config.server_list == ["[::1]:8848", "[::2]:8848"]


def test_sdk_settings_take_the_namespace_and_credentials_of_the_url(config):
    credentials = config.credentials_provider.get_credentials()

    assert (config.namespace_id, config.username, config.password) == ("dev", "u", "p")
    assert (credentials.get_access_key_id(), credentials.get_access_key_secret()) == ("ak", "sk")


def test_sdk_settings_take_the_timeout_of_the_url(config):
    assert (config.timeout_ms, config.grpc_config.grpc_timeout) == (1500, 1500)


def test_sdk_settings_keep_services_that_lose_every_instance(config):
    assert config.update_cache_when_empty


def test_sdk_settings_read_no_disk_cache_at_start(config):
    assert not config.load_cache_at_start


def test_sdk_rejects_a_timeout_that_is_not_positive():
    with pytest.raises(ValueError, match="positive"):
        client_config(URL.parse("nacos://n?timeout=0"))
