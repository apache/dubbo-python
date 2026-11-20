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

from dubbo import Result, RpcError, Status
from dubbo.filter.token import TokenFilter

pytestmark = pytest.mark.anyio


async def test_token_filter_calls_the_handler_when_the_token_matches(ending, call, url):
    end = ending(Result(value="ok"))

    result = await TokenFilter(url.update_parameters({"token": "s3"})).invoke(end.invoke, call(token="s3"))

    assert result == Result(value="ok")
    assert len(end.calls) == 1


@pytest.mark.parametrize("attachments", [{}, {"token": "s4"}], ids=["missing", "wrong"])
async def test_token_filter_denies_a_call_without_the_matching_token(attachments, ending, call, url):
    end = ending(Result(value="ok"))

    result = await TokenFilter(url.update_parameters({"token": "s3"})).invoke(end.invoke, call(**attachments))

    assert isinstance(result.error, RpcError)
    assert (result.error.status, result.error.message, end.calls) == (
        Status.PERMISSION_DENIED,
        "com.example.UserService.getUser needs its token",
        [],
    )
