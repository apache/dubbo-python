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

from collections.abc import Sequence

from dubbo.constants import REGISTRY_PREFERRED_KEY, REGISTRY_ZONE_FORCE_KEY, REGISTRY_ZONE_KEY
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.utils.converters import is_true

from .base import BaseCluster

__all__ = ["ZoneAwareCluster"]


class ZoneAwareCluster(BaseCluster):
    """Makes each call through the invoker of one of the registries of a reference.

    It takes the first available invoker whose URL sets
    ``registry.preferred`` to ``true``. Else, when the ``registry.zone``
    attachment of the call names a zone, it takes the first available
    invoker whose URL has that ``registry.zone``; finding none ends the call
    with ``UNAVAILABLE`` if the ``registry.zone.force`` attachment is
    ``true``. Else it takes the invoker the load balance chooses among the
    available ones, by the ``weight`` of its URL; when none is available,
    the call ends with ``UNAVAILABLE``.
    """

    async def _invoke(self, invocation: Invocation, invokers: Sequence[Invoker]) -> Result:
        for invoker in invokers:
            if invoker.available and is_true(invoker.url.parameters.get(REGISTRY_PREFERRED_KEY)):
                return await invoker.invoke(invocation)

        zone = invocation.attachments.get(REGISTRY_ZONE_KEY)
        if zone:
            for invoker in invokers:
                if invoker.available and invoker.url.parameters.get(REGISTRY_ZONE_KEY) == zone:
                    return await invoker.invoke(invocation)
            if is_true(invocation.attachments.get(REGISTRY_ZONE_FORCE_KEY)):
                error = RpcError(
                    Status.UNAVAILABLE, f"no provider of {invocation.interface} is available in zone {zone}"
                )
                return Result(error=error)

        chosen = self._select(invokers, invocation)
        if chosen.available:
            return await chosen.invoke(invocation)

        return Result(error=RpcError(Status.UNAVAILABLE, f"no provider of {invocation.interface} is available"))
