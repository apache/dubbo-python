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
from dubbo.configs import ReferenceConfig
from samples.proto import greeter_pb2


class GreeterServiceStub:
    def __init__(self, client: dubbo.Client):
        self.stream_unary = client.server_stream(
            method_name="serverStream",
            request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
            response_deserializer=greeter_pb2.GreeterReply.FromString,
        )

    def server_stream(self, values):
        return self.stream_unary(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url("tri://127.0.0.1:50051/org.apache.dubbo.samples.data.Greeter")
    dubbo_client = dubbo.Client(reference_config)
    stub = GreeterServiceStub(dubbo_client)

    stream = stub.server_stream(greeter_pb2.GreeterRequest(name="hello world from dubbo-python"))

    for i in stream:
        print(f"Received response: {i.message}")
