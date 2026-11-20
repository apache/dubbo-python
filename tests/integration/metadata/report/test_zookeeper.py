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

import uuid

import anyio
import pytest

from dubbo.extension import ApplicationScope
from dubbo.metadata.report.zookeeper import ZookeeperMetadataReport
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.zookeeper]


@pytest.fixture
async def root(zookeeper, delete_tree, zk):
    root = f"/dubbo-python-test-{uuid.uuid4().hex}"
    yield root
    async with zk(f"zookeeper://{zookeeper}") as client:
        await delete_tree(client, root)


async def test_mapping_updates_leave_out_names_that_are_not_utf8(zookeeper, root, zk):
    async with zk(f"zookeeper://{zookeeper}") as client:
        await client.set(f"{root}/mapping/test.Greeter", b"good-app,\xff\xfe")
    async with ApplicationScope() as scope:
        url = URL.parse(f"zookeeper://{zookeeper}?group={root}").replace(attributes={APPLICATION_SCOPE: scope})
        async with ZookeeperMetadataReport(url) as report:
            with anyio.fail_after(5):
                async with report.subscribe_service_app_mapping("test.Greeter") as mappings:
                    assert await anext(mappings) == {"good-app"}
