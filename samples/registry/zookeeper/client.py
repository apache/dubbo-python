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

import dubbo
from dubbo.configs import ReferenceConfig, RegistryConfig
from samples.data import greeter_pb2


class GreeterServiceStub:
    def __init__(self, client: dubbo.Client):
        self.unary = client.unary(
            method_name="sayHello",
            request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
            response_deserializer=greeter_pb2.GreeterReply.FromString,
        )

    def say_hello(self, request):
        return self.unary(request)


if __name__ == "__main__":
    registry_config = RegistryConfig.from_url("zookeeper://127.0.0.1:2181")
    bootstrap = dubbo.Dubbo(registry_config=registry_config)

    reference_config = ReferenceConfig(
        protocol="tri", service="org.apache.dubbo.samples.data.Greeter"
    )
    dubbo_client = bootstrap.create_client(reference_config)

    stub = GreeterServiceStub(dubbo_client)

    result = stub.say_hello(greeter_pb2.GreeterRequest(name="hello"))

    print(result.message)
