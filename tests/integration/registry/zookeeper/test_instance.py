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

import json

import pytest

from dubbo.extension import ApplicationScope
from dubbo.registry import ServiceInstance
from dubbo.registry.zookeeper import ZookeeperInstanceRegistry
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.zookeeper]


async def test_instance_registration_writes_the_curator_service_instance_format(real_registry_address, monkeypatch, zk):
    monkeypatch.setattr("time.time_ns", lambda: 1700000000000000000)
    instance = ServiceInstance(app="demo", host="10.0.0.5", port=50051, metadata={"dubbo.metadata.revision": "r1"})
    root = URL.parse(real_registry_address).parameters["group"]

    async with ApplicationScope() as scope:
        url = URL.parse(real_registry_address).replace(attributes={APPLICATION_SCOPE: scope})
        async with (
            ZookeeperInstanceRegistry(url) as registry,
            zk(real_registry_address) as client,
            registry.register(instance),
        ):
            data = await client.get(f"/{root}/demo/10.0.0.5:50051")

    assert json.loads(data) == {
        "name": "demo",
        "id": "10.0.0.5:50051",
        "address": "10.0.0.5",
        "port": 50051,
        "sslPort": None,
        "payload": {
            "@class": "org.apache.dubbo.registry.zookeeper.ZookeeperInstance",
            "id": "10.0.0.5:50051",
            "name": "demo",
            "metadata": {"dubbo.metadata.revision": "r1"},
        },
        "registrationTimeUTC": 1700000000000,
        "serviceType": "DYNAMIC",
        "uriSpec": None,
    }
