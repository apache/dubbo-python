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
from dubbo.configs import RegistryConfig, ServiceConfig
from dubbo.proxy.handlers import RpcMethodHandler, RpcServiceHandler
from samples.proto import greeter_pb2


class GreeterServiceServicer:
    def say_hello(self, request):
        print(f"Received request: {request.name}")
        return greeter_pb2.GreeterReply(message=f"Hello, {request.name}!")


def build_server_handler():
    # build a method handler
    method_handler = RpcMethodHandler.unary(
        GreeterServiceServicer().say_hello,
        method_name="sayHello",
        request_deserializer=greeter_pb2.GreeterRequest.FromString,
        response_serializer=greeter_pb2.GreeterReply.SerializeToString,
    )
    # build a service handler
    service_handler = RpcServiceHandler(
        service_name="org.apache.dubbo.samples.data.Greeter",
        method_handlers=[method_handler],
    )
    return service_handler


if __name__ == "__main__":
    registry_config = RegistryConfig.from_url("zookeeper://127.0.0.1:2181")
    bootstrap = dubbo.Dubbo(registry_config=registry_config)

    # build a service config
    service_handler = build_server_handler()
    service_config = ServiceConfig(service_handler)

    # start the server
    server = bootstrap.create_server(service_config).start()

    input("Press Enter to stop the server...\n")
