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
import time

import anyio

from dubbo.constants import GROUP_KEY, VERSION_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL

from .base import Filter

__all__ = ["AccessLogFilter"]

_logger = logging.getLogger("dubbo.accesslog")


class AccessLogFilter(Filter):
    """Logs each call to the service ``url`` as it ends, at INFO to the ``dubbo.accesslog`` logger, which the application configures.

    A line names the service by its ``group/interface:version`` key, then
    the method, the status the call ends with and how long it took, as in
    ``g/com.example.UserService:1.0 getUser OK 1.2ms``. A cancelled call
    ends with ``CANCELLED``, and one that raises with ``UNKNOWN``.

    Each record also holds these values as its fields, for a formatter that
    writes structured lines: ``service``, the interface; ``group`` and
    ``version``, ``None`` when the service has none; ``method``; ``status``,
    the name of the status; and ``duration_ms``, a float.
    """

    def __init__(self, url: URL) -> None:
        self._service = url.service_key
        self._fields = {
            "service": url.path,
            "group": url.parameters.get(GROUP_KEY),
            "version": url.parameters.get(VERSION_KEY),
        }

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        start = time.perf_counter()
        status = Status.UNKNOWN
        try:
            result = await call_next(invocation)
            error = result.error
            status = Status.OK if error is None else error.status if isinstance(error, RpcError) else Status.UNKNOWN
            return result
        except anyio.get_cancelled_exc_class():
            status = Status.CANCELLED
            raise
        finally:
            if _logger.isEnabledFor(logging.INFO):
                elapsed = (time.perf_counter() - start) * 1000
                _logger.info(
                    "%s %s %s %.1fms",
                    self._service,
                    invocation.method,
                    status.name,
                    elapsed,
                    extra={**self._fields, "method": invocation.method, "status": status.name, "duration_ms": elapsed},
                )
