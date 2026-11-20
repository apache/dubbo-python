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

import anyio
import pytest

from dubbo import Invocation, Invoker, Result
from dubbo.cluster import StaticDirectory
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_a_static_directory_closes_every_invoker_when_closing_one_is_cancelled(provider):
    first, last = provider("a"), provider("b")

    class Cancelling(Invoker):
        url = URL(protocol="tri", host="cancelling")

        async def invoke(self, invocation: Invocation) -> Result:
            return Result()

        async def aclose(self) -> None:
            scope.cancel()
            await anyio.sleep_forever()

    with anyio.fail_after(5), anyio.CancelScope() as scope:
        await StaticDirectory([first, Cancelling(), last]).aclose()

    assert (first.closed, last.closed) == (True, True)


async def test_a_static_directory_closes_every_invoker_when_closing_one_raises(provider):
    first, last = provider("a"), provider("b")

    class Failing(Invoker):
        url = URL(protocol="tri", host="failing")

        async def invoke(self, invocation: Invocation) -> Result:
            return Result()

        async def aclose(self) -> None:
            raise OSError("cannot close")

    with pytest.raises(OSError, match="cannot close"):
        await StaticDirectory([first, Failing(), last]).aclose()

    assert (first.closed, last.closed) == (True, True)
