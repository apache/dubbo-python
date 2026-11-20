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

import anyio
import pytest

from dubbo.extension import ApplicationScope
from dubbo.registry.zookeeper import ZookeeperInterfaceRegistry
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = [pytest.mark.anyio, pytest.mark.zookeeper]


@pytest.mark.parametrize(
    ("text", "node"),
    [
        (
            "tri://10.0.0.5:50051/com.example.Greeter?methods=a%2Cb&interface=com.example.Greeter",
            "tri%3A%2F%2F10.0.0.5%3A50051%2Fcom.example.Greeter%3Finterface%3Dcom.example.Greeter%26methods%3Da%2Cb",
        ),
        (
            "tri://alice:secret@10.0.0.5:50051/com.example.Greeter?side=provider",
            "tri%3A%2F%2Falice%3Asecret%4010.0.0.5%3A50051%2Fcom.example.Greeter%3Fside%3Dprovider",
        ),
    ],
    ids=["raw-comma-and-sorted-parameters", "credentials"],
)
async def test_registered_nodes_form_encode_the_full_unescaped_dubbo_url(real_registry_address, text, node, zk):
    root = URL.parse(real_registry_address).parameters["group"]
    async with ApplicationScope() as scope:
        url = URL.parse(real_registry_address).replace(attributes={APPLICATION_SCOPE: scope})
        async with (
            ZookeeperInterfaceRegistry(url) as registry,
            zk(real_registry_address) as client,
            registry.register(URL.parse(text)),
        ):
            assert await client.children(f"/{root}/com.example.Greeter/providers") == [node]


async def test_subscribers_decode_a_java_style_registry_node(real_registry_address, zk):
    interface = "org.apache.dubbo.demo.DemoService"
    node = (
        "dubbo%3A%2F%2F192.168.1.7%3A20880%2Forg.apache.dubbo.demo.DemoService%3Fanyhost%3Dtrue"
        "%26application%3Ddemo-provider%26interface%3Dorg.apache.dubbo.demo.DemoService"
        "%26methods%3DsayHello%2CsayHelloAsync%26side%3Dprovider%26timestamp%3D1700000000000"
    )
    root = URL.parse(real_registry_address).parameters["group"]
    async with ApplicationScope() as scope:
        url = URL.parse(real_registry_address).replace(attributes={APPLICATION_SCOPE: scope})
        async with ZookeeperInterfaceRegistry(url) as registry, zk(real_registry_address) as client:
            await client.create(f"/{root}/{interface}/providers/{node}")
            with anyio.fail_after(5):
                async with registry.subscribe(interface, group=None, version=None) as urls:
                    assert await anext(urls) == [
                        URL(
                            protocol="dubbo",
                            host="192.168.1.7",
                            port=20880,
                            path=interface,
                            parameters={
                                "anyhost": "true",
                                "application": "demo-provider",
                                "interface": interface,
                                "methods": "sayHello,sayHelloAsync",
                                "side": "provider",
                                "timestamp": "1700000000000",
                            },
                        )
                    ]
