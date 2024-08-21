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
import stream_unary_pb2

import dubbo
from dubbo.configs import ReferenceConfig


class ClientStreamServiceStub:

    def __init__(self, client: dubbo.Client):
        self.unary_stream = client.client_stream(
            method_name="clientStream",
            request_serializer=stream_unary_pb2.Request.SerializeToString,
            response_deserializer=stream_unary_pb2.Response.FromString,
        )

    def unary_stream(self, values):
        return self.unary_stream(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.stream"
    )
    dubbo_client = dubbo.Client(reference_config)

    client_stream_service_stub = ClientStreamServiceStub(dubbo_client)

    # Iterator of request
    def request_generator():
        for i in ["hello", "world", "from", "dubbo-python"]:
            yield stream_unary_pb2.Request(name=str(i))

    result = client_stream_service_stub.unary_stream(request_generator())

    print(result.message)
