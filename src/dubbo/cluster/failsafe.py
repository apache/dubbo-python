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
from collections.abc import Sequence

from dubbo.rpc.definition import RpcType
from dubbo.rpc.invocation import Invocation, Invoker, Result

from .base import BaseCluster

__all__ = ["FailsafeCluster"]

_logger = logging.getLogger(__name__)


class FailsafeCluster(BaseCluster):
    """Makes each call once, on the invoker the load balance chooses, and returns nothing instead of a failure.

    A unary call that fails, whatever the failure, is logged and returns
    ``None``. A streaming call returns how it opened.
    """

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        result = await self._select(invokers, invocation).invoke(invocation)
        if result.error is None or invocation.definition.rpc_type is not RpcType.UNARY:
            return result

        _logger.warning(
            "A call of %s.%s failed; it returns None instead",
            invocation.interface,
            invocation.method,
            exc_info=result.error,
        )
        return Result()
