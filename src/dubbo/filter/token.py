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

import hmac

from dubbo.constants import TOKEN_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL

from .base import Filter

__all__ = ["TokenFilter"]


class TokenFilter(Filter):
    """Refuses with ``PERMISSION_DENIED`` each call that does not attach the ``token`` of the service ``url``."""

    def __init__(self, url: URL) -> None:
        self._token = url.parameters.get(TOKEN_KEY, "").encode()

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        received = invocation.attachments.get(TOKEN_KEY)
        if self._token and not (isinstance(received, str) and hmac.compare_digest(received.encode(), self._token)):
            error = RpcError(Status.PERMISSION_DENIED, f"{invocation.interface}.{invocation.method} needs its token")
            return Result(error=error)

        return await call_next(invocation)
