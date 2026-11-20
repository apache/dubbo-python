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

"""How a consumer reads the metadata an instance serves through its MetadataService."""

from dubbo.constants import TIMEOUT_KEY
from dubbo.protocol import get_protocol
from dubbo.rpc.definition import get_definition
from dubbo.url import URL

from ..info import MetadataInfo
from ..instance import METADATA_SERVICE_V2

__all__ = ["call_metadata_service"]

# Milliseconds a call to the MetadataService of an instance may take, connecting included.
_METADATA_TIMEOUT = "5000"


async def call_metadata_service(url: URL, revision: str) -> MetadataInfo | None:
    """Return the metadata at ``revision`` of the MetadataService that ``url`` calls.

    The path of ``url`` selects MetadataServiceV2 or the MetadataService
    1.0.0. For a revision it does not serve, 1.0.0 gives ``None`` and
    MetadataServiceV2 fails with ``NOT_FOUND``. The call may take five
    seconds, connecting included.

    Raises:
        ValueError: The metadata cannot be read.
        DubboError: The call failed or took too long.
        OSError: The instance cannot be reached.
    """
    if url.path == METADATA_SERVICE_V2:
        from . import v2

        contract: type = v2.MetadataServiceV2
        read_metadata_info = v2.read_metadata_info
    else:
        from . import v1

        contract = v1.MetadataServiceV1
        read_metadata_info = v1.read_metadata_info

    url = url.update_parameters({TIMEOUT_KEY: _METADATA_TIMEOUT})
    invoker = await (await get_protocol(url.protocol, url.scope)).refer(url, get_definition(contract))
    try:
        return await read_metadata_info(invoker.invoke, revision)
    finally:
        await invoker.aclose()
