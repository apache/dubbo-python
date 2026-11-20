# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

import pytest

import dubbo.metadata.service.client as client
from dubbo.exceptions import RpcError, Status
from dubbo.extension import ApplicationScope
from dubbo.rpc import Result
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "path", ["org.apache.dubbo.metadata.MetadataServiceV2", "org.apache.dubbo.metadata.MetadataService"]
)
async def test_a_call_to_the_metadata_service_may_take_five_seconds(monkeypatch, path):
    referred = []

    class Invoker:
        async def invoke(self, invocation):
            return Result(error=RpcError(Status.UNAVAILABLE, "unreachable"))

        async def aclose(self):
            pass

    class Protocol:
        async def refer(self, url, definition):
            referred.append(url)
            return Invoker()

    async def get_protocol(name, scope):
        return Protocol()

    monkeypatch.setattr(client, "get_protocol", get_protocol)

    url = URL.parse(f"tri://10.0.0.5:50051/{path}?timeout=1000").replace(
        attributes={APPLICATION_SCOPE: ApplicationScope()}
    )
    with pytest.raises(RpcError):
        await client.call_metadata_service(url, "r1")

    # The time of a call is its URL's, which a consumer's own settings must not shorten.
    assert [url.parameters["timeout"] for url in referred] == ["5000"]
