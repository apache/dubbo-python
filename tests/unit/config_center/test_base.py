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

from dubbo.config_center import ConfigCenter, get_config_center
from dubbo.extension import ApplicationScope, extensions
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_an_application_shares_one_configuration_center_per_url(isolated_extensions):
    created = []

    class Center(ConfigCenter):
        def __init__(self, url):
            super().__init__(url)
            self.connected, self.closed = False, False
            created.append(self)

        async def __aenter__(self):
            self.connected = True
            return self

        async def aclose(self):
            self.closed = True

    extensions.register(ConfigCenter, "memory", Center)

    async with ApplicationScope() as scope:
        url = URL(protocol="memory", host="center", attributes={APPLICATION_SCOPE: scope})
        first = await get_config_center(url)
        assert await get_config_center(url) is first
        assert created == [first]
        assert (first.connected, first.closed) == (True, False)

    assert first.closed
    with pytest.raises(RuntimeError, match="belongs to no application"):
        await get_config_center(URL(protocol="memory", host="center"))
    assert created == [first]
