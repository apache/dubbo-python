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
from types import SimpleNamespace

import anyio
import pytest

from dubbo import Invocation, Result, RpcError, Status
from dubbo.filter import accesslog
from dubbo.filter.accesslog import AccessLogFilter

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("error", "parameters", "line"),
    [
        (None, {}, "com.example.UserService getUser OK 1.2ms"),
        (RpcError(Status.NOT_FOUND), {}, "com.example.UserService getUser NOT_FOUND 1.2ms"),
        (KeyError("u"), {}, "com.example.UserService getUser UNKNOWN 1.2ms"),
        (None, {"group": "g", "version": "1.0"}, "g/com.example.UserService:1.0 getUser OK 1.2ms"),
    ],
    ids=["success", "rpc-status", "handler-exception", "service-key"],
)
async def test_access_log_records_the_service_method_status_and_elapsed_time(
    error, parameters, line, monkeypatch, ending, call, url, caplog
):
    monkeypatch.setattr(accesslog, "time", SimpleNamespace(perf_counter=iter([1.0, 1.0012]).__next__))
    expected = Result(value="u", error=error)

    with caplog.at_level(logging.INFO, logger="dubbo.accesslog"):
        result = await AccessLogFilter(url.update_parameters(parameters)).invoke(ending(expected).invoke, call())

    assert result is expected
    assert [(record.name, record.levelno, record.getMessage()) for record in caplog.records] == [
        ("dubbo.accesslog", logging.INFO, line)
    ]


async def test_access_log_records_a_cancelled_call(monkeypatch, call, url, caplog):
    monkeypatch.setattr(accesslog, "time", SimpleNamespace(perf_counter=iter([1.0, 1.0012]).__next__))

    async def call_next(invocation: Invocation) -> Result:
        scope.cancel()
        await anyio.sleep_forever()

    with caplog.at_level(logging.INFO, logger="dubbo.accesslog"), anyio.CancelScope() as scope:
        await AccessLogFilter(url).invoke(call_next, call())

    assert [record.getMessage() for record in caplog.records] == ["com.example.UserService getUser CANCELLED 1.2ms"]


async def test_access_log_records_a_call_that_raises_and_lets_the_exception_through(monkeypatch, call, url, caplog):
    monkeypatch.setattr(accesslog, "time", SimpleNamespace(perf_counter=iter([1.0, 1.0012]).__next__))

    async def call_next(invocation: Invocation) -> Result:
        raise OSError("lost")

    with caplog.at_level(logging.INFO, logger="dubbo.accesslog"), pytest.raises(OSError, match="lost"):
        await AccessLogFilter(url).invoke(call_next, call())

    assert [record.getMessage() for record in caplog.records] == ["com.example.UserService getUser UNKNOWN 1.2ms"]


@pytest.mark.parametrize(
    ("parameters", "group", "version"),
    [({}, None, None), ({"group": "g", "version": "1.0"}, "g", "1.0")],
    ids=["plain", "group-and-version"],
)
async def test_access_log_gives_each_value_as_a_field_of_its_record(
    parameters, group, version, monkeypatch, ending, call, url, caplog
):
    monkeypatch.setattr(accesslog, "time", SimpleNamespace(perf_counter=iter([1.0, 1.0015]).__next__))

    with caplog.at_level(logging.INFO, logger="dubbo.accesslog"):
        await AccessLogFilter(url.update_parameters(parameters)).invoke(
            ending(Result(error=RpcError(Status.NOT_FOUND))).invoke, call()
        )

    [record] = caplog.records
    fields = {name: getattr(record, name) for name in ("service", "group", "version", "method", "status")}
    assert fields == {
        "service": "com.example.UserService",
        "group": group,
        "version": version,
        "method": "getUser",
        "status": "NOT_FOUND",
    }
    assert record.duration_ms == pytest.approx(1.5)
