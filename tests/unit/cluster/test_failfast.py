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

pytestmark = pytest.mark.anyio


async def test_failfast_returns_the_failure_without_retrying(provider, unavailable, open_cluster, call):
    failed = provider("a", unavailable)

    async with open_cluster("failfast", failed) as cluster:
        result = await cluster.invoke(call)

    assert (result, failed.calls) == (unavailable, 1)
