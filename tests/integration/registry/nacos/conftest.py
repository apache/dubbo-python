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

import uuid
from contextlib import AsyncExitStack

import pytest

from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, URL


@pytest.fixture
def group():
    return f"dubbo-test-{uuid.uuid4().hex}"


@pytest.fixture
def provider_url():
    interface = f"org.example.Users${uuid.uuid4().hex}"
    return URL.parse(f"tri://10.0.0.1:50051/{interface}?interface={interface}&version=1.0.0&group=blue&side=provider")


@pytest.fixture
async def opened(nacos):
    async with AsyncExitStack() as stack:

        async def open_registry(cls, query=""):
            scope = await stack.enter_async_context(ApplicationScope())
            url = URL.parse(f"nacos://{nacos}?{query}").replace(attributes={APPLICATION_SCOPE: scope})
            return await stack.enter_async_context(cls(url))

        yield open_registry


@pytest.fixture
async def register(opened):
    """Keep a URL or instance registered with a registry until the test ends, or the function returned releases it."""
    kept = []

    async def register_url(registry, url):
        stack = AsyncExitStack()
        await stack.enter_async_context(registry.register(url))
        kept.append(stack)
        return stack.aclose

    yield register_url

    for stack in reversed(kept):
        await stack.aclose()
