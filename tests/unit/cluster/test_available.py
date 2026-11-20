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

pytestmark = pytest.mark.anyio


async def test_available_calls_only_the_first_available_provider(provider, open_cluster, call):
    down, first, second = provider("down", up=False), provider("first"), provider("second")

    async with open_cluster("available", down, first, second) as cluster:
        results = [await cluster.invoke(call) for _ in range(2)]

    assert ([result.value for result in results], down.calls, first.calls, second.calls) == (
        ["first", "first"],
        0,
        2,
        0,
    )


async def test_available_refuses_to_call_unavailable_providers(provider, open_cluster, call):
    down = provider("down", up=False)

    async with open_cluster("available", down) as cluster:
        result = await cluster.invoke(call)

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message, down.calls) == (
        Status.UNAVAILABLE,
        "no provider of test.Greeter is available",
        0,
    )
