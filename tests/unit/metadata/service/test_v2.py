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

from dubbo import RpcError, Status
from dubbo.metadata.service.server import MetadataStore

pytestmark = pytest.mark.anyio


async def test_the_metadata_service_serves_no_openapi_document():
    from dubbo.metadata.service.v2 import MetadataServiceV2Server, OpenAPIRequest

    with pytest.raises(RpcError, match="OpenAPI documents are not served") as raised:
        await MetadataServiceV2Server(MetadataStore()).get_open_api_info(OpenAPIRequest())

    assert raised.value.status is Status.UNIMPLEMENTED
