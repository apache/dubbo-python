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
from v2.nacos import ConfigParam

from dubbo.extension import ApplicationScope
from dubbo.metadata import MetadataInfo
from dubbo.metadata.report.nacos import NacosMetadataReport
from dubbo.transport.nacos import get_nacos_config_client
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.nacos]


@pytest.fixture
async def storage(nacos):
    app, interface = f"orders-{uuid.uuid4().hex}", f"org.example.Users{uuid.uuid4().hex}"
    async with ApplicationScope() as scope:
        url = URL.parse(f"nacos://{nacos}").replace(attributes={APPLICATION_SCOPE: scope})
        client = await get_nacos_config_client(url)
        async with NacosMetadataReport(url) as report:
            yield report, client, app, interface

        # The framework has no configuration deletion API.
        for data_id, group in ((app, "0"), (interface, "mapping")):
            await client._connected().remove_config(ConfigParam(data_id=data_id, group=group))


async def test_app_metadata_is_stored_under_its_application_and_revision(storage):
    report, client, app, _ = storage
    metadata = MetadataInfo(app=app)

    assert await report.get_app_metadata(app, metadata.revision) is None
    with anyio.fail_after(10):
        async with client.watch(app, metadata.revision) as contents:
            assert await anext(contents) is None
            await report.publish_app_metadata(metadata)
            async for content in contents:
                if content == metadata.to_json():
                    break

    assert content == metadata.to_json()
    assert await client.get(app, metadata.revision) == metadata.to_json()
    assert await report.get_app_metadata(app, metadata.revision) == metadata


async def test_publishing_metadata_preserves_an_existing_revision(storage):
    report, client, app, _ = storage
    metadata = MetadataInfo(app=app)
    with anyio.fail_after(10):
        async with client.watch(app, metadata.revision) as contents:
            assert await anext(contents) is None
            await client.update(app, metadata.revision, lambda _: "stored first")
            async for content in contents:
                if content == "stored first":
                    break

    await report.publish_app_metadata(metadata)

    assert await client.get(app, metadata.revision) == "stored first"


async def test_interface_mapping_stores_unique_application_names_in_the_mapping_group(storage):
    report, client, _, interface = storage

    with anyio.fail_after(10):
        async with report.subscribe_service_app_mapping(interface) as names:
            assert await anext(names) == frozenset()
            for app in ("orders", "billing", "orders"):
                await report.register_service_app_mapping(interface, app)
            async for applications in names:
                if applications == {"orders", "billing"}:
                    break

    assert applications == {"orders", "billing"}
    assert await client.get(interface, "mapping") == "orders,billing"
