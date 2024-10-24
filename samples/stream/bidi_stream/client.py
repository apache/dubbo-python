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
from dubbo.classes import EOF
from dubbo.configs import ReferenceConfig
from samples.proto import greeter_pb2


class GreeterServiceStub:
    def __init__(self, client: dubbo.Client):
        self.bidi_stream = client.bidi_stream(
            method_name="biStream",
            request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
            response_deserializer=greeter_pb2.GreeterReply.FromString,
        )

    def bi_stream(self, *args):
        return self.bidi_stream(args)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.proto.Greeter"
    )
    dubbo_client = dubbo.Client(reference_config)

    stub = GreeterServiceStub(dubbo_client)

    # # Iterator of request
    # def request_generator():
    #     for item in ["hello", "world", "from", "dubbo-python"]:
    #         yield greeter_pb2.GreeterRequest(name=str(item))
    #
    # result = stub.bi_stream(request_generator())
    #
    # for i in result:
    #     print(f"Received response: {i.message}")

    stream = stub.bi_stream()

    stream.write(greeter_pb2.GreeterRequest(name="hello"))

    # print(f"Received response: {stream.read().message}")

    stream.write(greeter_pb2.GreeterRequest(name="world"))
    stream.write(greeter_pb2.GreeterRequest(name="from"))
    stream.write(greeter_pb2.GreeterRequest(name="dubbo-python"))
    stream.done_writing()

    # 直接调用read方法
    print(stream.read())

    # 迭代器调用read方法（推荐）
    for i in stream:
        print(f"Received response: {i.message}")

    # 循环调用read方法
    while True:
        i = stream.read(timeout=0.5)
        if i is EOF:
            break
        elif i is None:
            print("No message received")
            continue
        print(f"Received response: {i.message}")
