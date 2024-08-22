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


class UnaryServiceStub:

    def __init__(self, client: dubbo.Client):
        self.unary = client.unary(method_name="unary")

    def unary(self, request):
        return self.unary(request)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.HelloWorld"
    )
    dubbo_client = dubbo.Client(reference_config)

    unary_service_stub = UnaryServiceStub(dubbo_client)

    result = unary_service_stub.unary("hello".encode("utf-8"))
    print(result.decode("utf-8"))
