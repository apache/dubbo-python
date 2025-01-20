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

from dubbo.classes import MethodDescriptor
from dubbo.constants import common_constants
from dubbo.protocol import Invoker
from dubbo.protocol.invocation import RpcInvocation
from dubbo.proxy import RpcCallable, RpcCallableFactory
from dubbo.url import URL

__all__ = ["MultipleRpcCallable", "DefaultRpcCallableFactory"]

from dubbo.proxy.handlers import RpcServiceHandler


class MultipleRpcCallable(RpcCallable):
    """
    The RpcCallable class.
    """

    def __init__(self, invoker: Invoker, url: URL):
        self._invoker = invoker
        self._url = url

        self._method_model: MethodDescriptor = url.attributes[common_constants.METHOD_DESCRIPTOR_KEY]

        self._service_name = url.path
        self._method_name = self._method_model.get_method_name()

    def _create_invocation(self, argument: Any) -> RpcInvocation:
        return RpcInvocation(
            self._service_name,
            self._method_name,
            argument,
            attributes={common_constants.METHOD_DESCRIPTOR_KEY: self._method_model},
        )

    def __call__(self, *args, **kwargs) -> Any:
        # Create a new RpcInvocation
        invocation = self._create_invocation((args, kwargs))
        # Do invoke.
        result = self._invoker.invoke(invocation)
        return result.value()


class DefaultRpcCallableFactory(RpcCallableFactory):
    """
    The RpcCallableFactory class.
    """

    def get_callable(self, invoker: Invoker, url: URL) -> RpcCallable:
        return MultipleRpcCallable(invoker, url)

    def get_invoker(self, service_handler: RpcServiceHandler, url: URL) -> Invoker:
        pass
