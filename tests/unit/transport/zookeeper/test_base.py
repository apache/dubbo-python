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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import attrs
import pytest

from dubbo.extension import ApplicationScope, extensions
from dubbo.transport import zookeeper
from dubbo.transport.zookeeper import ZookeeperClient
from dubbo.transport.zookeeper.kazoo import KazooZookeeperClient
from dubbo.url import APPLICATION_SCOPE, URL


@attrs.define(kw_only=False)
class _Recorder:
    """A ZookeeperClient registered as ``recorder`` that keeps the URLs it is created with."""

    urls: list[URL] = attrs.field(factory=list)

    @asynccontextmanager
    async def create(self, url: URL) -> AsyncIterator[object]:
        self.urls.append(url)
        yield object()


@pytest.fixture
def recorder(isolated_extensions) -> _Recorder:
    recorder = _Recorder()
    extensions.register(ZookeeperClient, "recorder", recorder.create)
    return recorder


@pytest.mark.anyio
async def test_users_of_the_same_connection_share_one_client_within_an_application(recorder):
    # A registry, and the configuration center it serves as, which has a timeout of its own.
    texts = [
        "zookeeper://zk?client=recorder&namespace=a",
        "zookeeper://zk/path?client=recorder&group=b&timeout=30000",
        "zookeeper://zk?client=recorder&session=5000",
    ]

    async with ApplicationScope() as scope:
        first, second, other = [URL.parse(text).replace(attributes={APPLICATION_SCOPE: scope}) for text in texts]
        a, b, c = [await zookeeper.get_zookeeper_client(url) for url in (first, second, other)]
        assert a is b
        assert c is not a

    assert recorder.urls == [first, other]


@pytest.mark.anyio
async def test_a_client_belongs_to_an_application(recorder):
    with pytest.raises(RuntimeError, match="belongs to no application"):
        await zookeeper.get_zookeeper_client(URL.parse("zookeeper://zk?client=recorder"))

    assert recorder.urls == []


@pytest.mark.anyio
async def test_connect_needs_a_host(recorder):
    with pytest.raises(ValueError, match="needs a host"):
        await zookeeper.get_zookeeper_client(URL.parse("zookeeper:///path?client=recorder"))

    assert recorder.urls == []


def test_kazoo_is_the_installed_client_and_the_default():
    assert extensions.get(ZookeeperClient, "kazoo") is KazooZookeeperClient
    assert extensions.get(ZookeeperClient, None) is KazooZookeeperClient
