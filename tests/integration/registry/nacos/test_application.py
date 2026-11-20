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

import typing
import uuid

import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, RegistryConfig, RegistryMode, ShutdownConfig

pytestmark = [pytest.mark.anyio, pytest.mark.nacos]


@dubbo.service("test.nacos.Greeter")
class Greeter(typing.Protocol):
    @dubbo.method("Greet")
    async def greet(self, request: StringValue) -> StringValue: ...


class GreeterImpl(Greeter):
    async def greet(self, request: StringValue) -> StringValue:
        return StringValue(value=f"hello {request.value}")


@pytest.mark.parametrize("mode", [RegistryMode.INTERFACE, RegistryMode.INSTANCE])
async def test_a_consumer_calls_a_provider_found_in_nacos(mode, nacos):
    group = f"test-{uuid.uuid4().hex}"
    registry = RegistryConfig(address=f"nacos://{nacos}", group=group, mode=mode)
    app = Dubbo(
        application=ApplicationConfig(name=f"greeter-{group}"),
        registries={"nacos": registry},
        protocols={"tri": ProtocolConfig(name="tri", host="127.0.0.1", port=0)},
        shutdown=ShutdownConfig(unregister_wait=0),
        env_prefix=None,
    )
    app.export(GreeterImpl())
    caller = Dubbo(
        application=ApplicationConfig(name=f"caller-{group}"), registries={"nacos": registry}, env_prefix=None
    )
    greeter = caller.refer(Greeter)

    async with app, caller:
        assert await greeter.greet(StringValue(value="nacos")) == StringValue(value="hello nacos")
