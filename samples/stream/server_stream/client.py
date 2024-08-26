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
import unary_stream_pb2

import dubbo
from dubbo.configs import ReferenceConfig


class ServerStreamServiceStub:

    def __init__(self, client: dubbo.Client):
        self.stream_unary = client.server_stream(
            method_name="serverStream",
            request_serializer=unary_stream_pb2.Request.SerializeToString,
            response_deserializer=unary_stream_pb2.Response.FromString,
        )

    def stream_unary(self, values):
        return self.stream_unary(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.stream"
    )
    dubbo_client = dubbo.Client(reference_config)

    server_stream_service_stub = ServerStreamServiceStub(dubbo_client)

    request = unary_stream_pb2.Request(name="hello world from dubbo-python")

    result = server_stream_service_stub.stream_unary(request)

    for i in result:
        print(f"Received response: {i.message}")
