#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import inspect
from typing import Any

from dubbo.common.constants import common_constants
from dubbo.common.url import URL
from dubbo.protocol.invocation import RpcInvocation
from dubbo.protocol.invoker import Invoker


class RpcCallable:

    def __init__(self, invoker: Invoker, url: URL):
        self._invoker = invoker
        self._url = url
        self._service_name = self._url.path or ""
        method_url = self._url.get_attribute(common_constants.METHOD_KEY)
        self._method_name = method_url.get_parameter(common_constants.METHOD_KEY) or ""
        self._call_type = method_url.get_parameter(common_constants.TYPE_CALL)
        self._req_serializer = (
            method_url.get_attribute(common_constants.SERIALIZATION) or None
        )
        self._res_serializer = (
            method_url.get_attribute(common_constants.SERIALIZATION) or None
        )

    async def _do_call(self, argument: Any):
        """
        Real call method.
        """
        if (
            self._call_type == common_constants.CALL_CLIENT_STREAM
            and not inspect.isgeneratorfunction(argument)
        ):
            raise ValueError(
                "Invalid argument: The provided argument must be a generator function "
            )
        elif (
            self._call_type == common_constants.CALL_UNARY
            and inspect.isgeneratorfunction(argument)
        ):
            raise ValueError(
                "Invalid argument: The provided argument must be a normal function"
            )

        # Create a new RpcInvocation object.
        invocation = RpcInvocation(
            self._service_name,
            self._method_name,
            argument,
            self._req_serializer,
            self._res_serializer,
        )
        # Do invoke.
        result = self._invoker.invoke(invocation)
        return result

    async def __call__(self, argument: Any):
        return await self._do_call(argument)


class AsyncRpcCallable:

    async def __call__(self, *args, **kwargs):
        pass
