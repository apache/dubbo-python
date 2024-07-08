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
from typing import Any

from dubbo.constants import common_constants
from dubbo.protocol.invocation import RpcInvocation
from dubbo.protocol.invoker import Invoker
from dubbo.url import URL


class RpcCallable:

    def __init__(self, invoker: Invoker, url: URL):
        self._invoker = invoker
        self._url = url
        self._service_name = self._url.path or ""
        self._method_name = self._url.get_parameter(common_constants.METHOD_KEY) or ""
        self._call_type = self._url.get_parameter(common_constants.CALL_KEY)
        self._request_serializer = (
            self._url.get_attribute(common_constants.SERIALIZATION) or None
        )
        self._response_serializer = (
            self._url.get_attribute(common_constants.DESERIALIZATION) or None
        )

    def _do_call(self, argument: Any) -> Any:
        """
        Real call method.
        """
        # Create a new RpcInvocation object.
        invocation = RpcInvocation(
            self._service_name,
            self._method_name,
            argument,
            attributes={
                common_constants.CALL_KEY: self._call_type,
                common_constants.SERIALIZATION: self._request_serializer,
                common_constants.DESERIALIZATION: self._response_serializer,
            },
        )
        # Do invoke.
        result = self._invoker.invoke(invocation)
        return result.get_value()

    def __call__(self, argument: Any) -> Any:
        return self._do_call(argument)
