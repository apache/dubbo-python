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
from dubbo.configs import ServiceConfig
from dubbo.proxy.handlers import RpcMethodHandler, RpcServiceHandler
from samples.proto import greeter_pb2

import time


class GreeterServiceServicer:
    def bi_stream(self, stream):
        counter = 0
        for request in stream:
            print(f"Received request: {request.name}")
            # simulate a long time to process
            if counter == 1:
                time.sleep(1)
            counter += 1

            stream.write(greeter_pb2.GreeterReply(message=f"Hello, {request.name}!"))

        stream.done_writing()


def build_server_handler():
    method_handler = RpcMethodHandler.bi_stream(
        GreeterServiceServicer().bi_stream,
        method_name="biStream",
        request_deserializer=greeter_pb2.GreeterRequest.FromString,
        response_serializer=greeter_pb2.GreeterReply.SerializeToString,
    )
    service_handler = RpcServiceHandler(
        service_name="org.apache.dubbo.samples.data.Greeter",
        method_handlers=[method_handler],
    )
    return service_handler


if __name__ == "__main__":
    # build a service config
    service_handler = build_server_handler()
    service_config = ServiceConfig(service_handler, host="127.0.0.1", port=50051)

    # start the server
    server = dubbo.Server(service_config).start()

    input("Press Enter to stop the server...\n")
