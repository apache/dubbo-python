#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import time

import unary_unary_pb2

import dubbo
from dubbo.configs import ReferenceConfig, RegistryConfig


class UnaryServiceStub:

    def __init__(self, client: dubbo.Client):
        self.unary = client.unary(
            method_name="unary",
            request_serializer=unary_unary_pb2.Request.SerializeToString,
            response_deserializer=unary_unary_pb2.Response.FromString,
        )

    def unary(self, request):
        return self.unary(request)


if __name__ == "__main__":
    registry_config = RegistryConfig.from_url(
        "zookeeper://127.0.0.1:2181?loadbalance=cpu"
    )
    bootstrap = dubbo.Dubbo(registry_config=registry_config)

    reference_config = ReferenceConfig(
        protocol="tri", service="org.apache.dubbo.samples.registry.zk"
    )
    dubbo_client = bootstrap.create_client(reference_config)

    unary_service_stub = UnaryServiceStub(dubbo_client)

    time.sleep(5)

    result = unary_service_stub.unary(unary_unary_pb2.Request(name="world"))

    print(result.message)

    time.sleep(10)

    result = unary_service_stub.unary(unary_unary_pb2.Request(name="world"))
    print(result.message)
