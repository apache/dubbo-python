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

import logging

import pytest

from dubbo import Result
from dubbo.extension import ApplicationScope
from dubbo.filter.deprecated import DeprecatedFilter
from dubbo.url import APPLICATION_SCOPE, URL

pytestmark = pytest.mark.anyio


async def test_deprecated_warns_once_per_method_and_application_across_provider_addresses(ending, call, caplog):
    url = URL.parse("tri://10.0.0.5:50051/test.Deprecating?deprecated=true&kept.deprecated=false")
    first, second = (url.replace(attributes={APPLICATION_SCOPE: ApplicationScope()}) for _ in range(2))
    filters = [DeprecatedFilter(first), DeprecatedFilter(first.replace(host="10.0.0.6")), DeprecatedFilter(second)]
    end = ending(Result())

    with caplog.at_level(logging.WARNING, logger="dubbo.filter.deprecated"):
        for filter_ in (filters[0], *filters):
            await filter_.invoke(end.invoke, call("old"))
            await filter_.invoke(end.invoke, call("kept"))

    assert [(record.name, record.levelno, record.getMessage()) for record in caplog.records] == [
        (
            "dubbo.filter.deprecated",
            logging.WARNING,
            "Calling test.Deprecating.old, which its provider at 10.0.0.5:50051 deprecates",
        )
    ] * 2
    assert [invocation.method for invocation in end.calls] == ["old", "kept"] * 4
