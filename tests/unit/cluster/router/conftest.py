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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest

from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE, CONFIG_CENTER_URL, URL


@pytest.fixture
def provider(provider):
    def create(host: str, query: str = "", port: int = 20880, app: str = "greeter"):
        return provider(host, query=f"remote.application={app}&{query}", port=port)

    return create


@pytest.fixture
def routed():
    @asynccontextmanager
    async def open_(
        router: type,
        consumer: str = "consumer://10.0.0.1/test.Greeter?application=web&version=1.0",
        *,
        center: bool = True,
    ) -> AsyncIterator:
        with anyio.fail_after(5):
            async with ApplicationScope() as scope:
                attributes: dict[str, object] = {APPLICATION_SCOPE: scope}
                if center:
                    attributes[CONFIG_CENTER_URL] = URL(protocol="memory", attributes={APPLICATION_SCOPE: scope})
                url = URL.parse(consumer).replace(attributes=attributes)

                async with router(url) as routing:
                    yield routing

    return open_
