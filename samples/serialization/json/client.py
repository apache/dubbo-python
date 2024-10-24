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

import orjson

import dubbo
from dubbo.configs import ReferenceConfig


def request_serializer(name: str, age: int) -> bytes:
    return orjson.dumps({"name": name, "age": age})


def response_deserializer(data: bytes) -> str:
    json_dict = orjson.loads(data)
    return json_dict["message"]


class GreeterServiceStub:
    def __init__(self, client: dubbo.Client):
        self.unary = client.unary(
            method_name="unary",
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )

    def say_hello(self, name: str, age: int):
        return self.unary(name, age)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.serialization.json"
    )
    dubbo_client = dubbo.Client(reference_config)

    stub = GreeterServiceStub(dubbo_client)
    result = stub.say_hello("dubbo-python", 18)
    print(result)
