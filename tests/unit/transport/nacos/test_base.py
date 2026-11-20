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

from contextlib import asynccontextmanager

import pytest

from dubbo.extension import ApplicationScope, extensions
from dubbo.transport.nacos import NacosConfigClient, NacosNamingClient, get_nacos_config_client, get_nacos_naming_client
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_users_of_one_connection_share_a_client_of_each_kind_within_an_application(isolated_extensions):
    opened, closed = [], []

    @asynccontextmanager
    async def connect(url):
        client = object()
        opened.append((url, client))
        yield client
        closed.append(client)

    extensions.register(NacosNamingClient, "recorder", lambda url: connect(url))
    extensions.register(NacosConfigClient, "recorder", lambda url: connect(url))
    async with ApplicationScope() as scope:
        url = URL.parse("nacos://n:8848?client=recorder&namespace=dev").replace(attributes={APPLICATION_SCOPE: scope})
        other = url.update_parameters({"namespace": "test"})

        naming = await get_nacos_naming_client(url)
        assert await get_nacos_naming_client(url.replace(path="x")) is naming
        assert await get_nacos_naming_client(url.update_parameters({"timeout": "30000"})) is naming
        config = await get_nacos_config_client(url)
        assert config is not naming
        assert await get_nacos_config_client(other) is not config
        assert closed == []

    assert [url for url, _ in opened] == [url, url, other]
    assert set(closed) == {client for _, client in opened}
