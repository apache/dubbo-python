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
        self.unary_stream = client.client_stream(
            method_name="clientStream",
            request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
            response_deserializer=greeter_pb2.GreeterReply.FromString,
        )

    def client_stream(self, request_iterator):
        return self.unary_stream(request_iterator)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url("tri://127.0.0.1:50051/org.apache.dubbo.samples.data.Greeter")
    dubbo_client = dubbo.Client(reference_config)
    stub = GreeterServiceStub(dubbo_client)

    # use iterator to send multiple requests
    def request_generator():
        for i in ["hello", "world", "from", "dubbo-python"]:
            yield greeter_pb2.GreeterRequest(name=str(i))

    # call the remote method and return a read_stream
    stream = stub.client_stream(request_generator())
    # use read method to get the response
    print(stream.read())
