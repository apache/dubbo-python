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

from pathlib import Path
from typing import Any

import pytest

from dubbo.metadata import MetadataInfo, ServiceInfo
from dubbo.metadata.service.server import MetadataStore
from dubbo.metadata.service.v1 import (
    JavaMetadataInfo,
    JavaServiceInfo,
    MetadataServiceV1,
    MetadataServiceV1Server,
    read_metadata_info,
)
from dubbo.rpc.definition import get_definition
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.url import URL

pytestmark = pytest.mark.anyio
_DATA = Path(__file__).parent / "data"
_ORDERS = MetadataInfo.from_services(
    "orders-app",
    [
        ServiceInfo(
            name="com.example.OrderService",
            group="g1",
            version="2.0.0",
            protocol="dubbo",
            port=20881,
            path="com.example.OrderService",
            params={"application": "orders-app", "methods": "find,list", "side": "provider"},
        ),
        ServiceInfo(name="com.example.Health", protocol="dubbo", port=20881, path="com.example.Health"),
    ],
)


def _response_codec():
    (method,) = (method for method in get_definition(MetadataServiceV1).methods if method.name == "getMetadataInfo")
    return Hessian2Serialization(URL.parse("dubbo://127.0.0.1")).codec([method.response])


def _returning(value: Any) -> Invoke:
    async def invoke(invocation: Invocation) -> Result:
        return Result(value=value)

    return invoke


async def test_the_metadata_java_serves_reads_as_its_services() -> None:
    (value,) = _response_codec().decode((_DATA / "metadata_info_java.hessian").read_bytes())

    info = await read_metadata_info(_returning(value), "b7b1f9e4c0d8a3d6e5f2a1b0c9d8e7f6")

    demo = ServiceInfo(
        name="org.apache.dubbo.demo.DemoService",
        group="g1",
        version="1.0.0",
        protocol="dubbo",
        port=20880,
        path="org.apache.dubbo.demo.DemoService",
        params={"application": "demo-provider", "methods": "sayHello,sayHelloAsync", "side": "provider"},
    )
    greeter = ServiceInfo(
        name="org.apache.dubbo.demo.GreeterService",
        protocol="tri",
        port=-1,
        path="org.apache.dubbo.demo.GreeterService",
    )
    assert info == MetadataInfo.from_services("demo-provider", [demo, greeter])


async def test_served_metadata_travels_as_java_reads_it() -> None:
    metadata = MetadataStore()
    metadata.add(_ORDERS)

    value = await MetadataServiceV1Server(metadata, "orders-app").get_metadata_info(_ORDERS.revision)

    assert _response_codec().encode((value,)) == (_DATA / "metadata_info_python.hessian").read_bytes()


async def test_a_revision_not_served_is_answered_with_none() -> None:
    metadata = MetadataStore()
    metadata.add(_ORDERS)

    assert await MetadataServiceV1Server(metadata, "orders-app").get_metadata_info("other") is None
    assert await read_metadata_info(_returning(None), "other") is None


async def test_the_server_answers_the_other_methods_java_calls() -> None:
    metadata = MetadataStore()
    metadata.add(_ORDERS)
    server = MetadataServiceV1Server(metadata, "orders-app")

    assert await server.service_name() == "orders-app"
    assert await server.version() == "1.0.0"
    assert await server.get_service_definition("g1/com.example.OrderService:2.0.0") == ""
    assert await server.get_metadata_infos() == [await server.get_metadata_info(_ORDERS.revision)]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(JavaMetadataInfo(revision="r", services={}), id="no-application"),
        pytest.param(
            JavaMetadataInfo(app="a", revision="r", services={"k": JavaServiceInfo(name="x.Y", port=1)}),
            id="service-without-protocol",
        ),
    ],
)
async def test_metadata_that_misses_what_names_a_service_cannot_be_read(value: JavaMetadataInfo) -> None:
    with pytest.raises(ValueError, match="the metadata"):
        await read_metadata_info(_returning(value), "r")
