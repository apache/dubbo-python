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
import uuid

import chat_pb2

import dubbo
from dubbo.configs import ReferenceConfig


class ChatServiceStub:

    def __init__(self, client: dubbo.Client):
        self.chat = client.bidi_stream(
            method_name="chat",
            request_serializer=chat_pb2.ChatMessage.SerializeToString,
            response_deserializer=chat_pb2.ChatMessage.FromString,
        )

    def chat(self, values):
        return self.chat(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.stream"
    )
    dubbo_client = dubbo.Client(reference_config)

    chat_service_stub = ChatServiceStub(dubbo_client)

    # Iterator of request
    def request_generator():
        for item in ["hello", "world", "from", "dubbo-python"]:
            yield chat_pb2.ChatMessage(user=item, message=str(uuid.uuid4()))

    result = chat_service_stub.chat(request_generator())

    for i in result:
        print(f"Received response: user={i.user}, message={i.message}")
