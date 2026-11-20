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

# Three filters: one that attaches an API key to the calls of a consumer, one
# that checks it on the provider, and one that times the calls a provider
# serves. register() gives them their names.

import logging
import time

from dubbo import Invocation, Invoke, Result, RpcError, Status
from dubbo.extension import extensions
from dubbo.filter import Filter
from dubbo.url import URL

_logger = logging.getLogger(__name__)

API_KEY = "api-key"


class ApiKeyFilter(Filter):
    """Attaches the API key of the reference to each of its calls."""

    # A filter is created with the URL of what it runs around, and reads its
    # settings from it once: here the api-key parameter of the reference.
    def __init__(self, url: URL) -> None:
        self.key = url.parameters[API_KEY]

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        invocation.attachments[API_KEY] = self.key
        return await call_next(invocation)


class ApiKeyCheckFilter(Filter):
    """Refuses the calls that do not attach the API key of the service."""

    def __init__(self, url: URL) -> None:
        self.key = url.parameters[API_KEY]

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        if invocation.attachments.get(API_KEY) != self.key:
            # A filter fails a call by returning an error, without calling on.
            error = RpcError(Status.PERMISSION_DENIED, "a valid API key is required")
            return Result(error=error)
        return await call_next(invocation)


class TimingFilter(Filter):
    """Logs how long each call takes, and how it ended."""

    def __init__(self, url: URL) -> None:
        self.service = url.path

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        start = time.perf_counter()
        result = await call_next(invocation)
        outcome = "failed" if result.error else "succeeded"
        elapsed = (time.perf_counter() - start) * 1000
        _logger.info("%s.%s %s in %.1f ms", self.service, invocation.method, outcome, elapsed)
        return result


def register() -> None:
    """Give the filters the names that configuration selects them by."""
    extensions.register(Filter, "api-key", ApiKeyFilter)
    extensions.register(Filter, "api-key-check", ApiKeyCheckFilter)
    extensions.register(Filter, "timing", TimingFilter)
