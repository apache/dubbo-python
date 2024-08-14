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

import abc

from dubbo.protocol import Invoker
from dubbo.proxy.handlers import RpcServiceHandler
from dubbo.url import URL

__all__ = ["RpcCallable", "RpcCallableFactory"]


class RpcCallable(abc.ABC):

    @abc.abstractmethod
    def __call__(self, *args, **kwargs):
        """
        call the rpc service
        """
        raise NotImplementedError()


class RpcCallableFactory(abc.ABC):

    @abc.abstractmethod
    def get_callable(self, invoker: Invoker, url: URL) -> RpcCallable:
        """
        get the rpc proxy
        :param invoker: the invoker.
        :type invoker: Invoker
        :param url: the url.
        :type url: URL
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_invoker(self, service_handler: RpcServiceHandler, url: URL) -> Invoker:
        """
        get the rpc invoker
        :param service_handler: the service handler.
        :type service_handler: RpcServiceHandler
        :param url: the url.
        :type url: URL
        """
        raise NotImplementedError()
