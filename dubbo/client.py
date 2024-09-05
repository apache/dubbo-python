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
import threading
from typing import Optional

from dubbo.bootstrap import Dubbo
from dubbo.configs import ReferenceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Invoker, Protocol
from dubbo.proxy import RpcCallable
from dubbo.proxy.callables import MultipleRpcCallable
from dubbo.registry.protocol import RegistryProtocol
from dubbo.types import (
    BiStreamCallType,
    CallType,
    ClientStreamCallType,
    DeserializingFunction,
    SerializingFunction,
    ServerStreamCallType,
    UnaryCallType,
)

__all__ = ["Client"]

from dubbo.url import URL


class Client:
    def __init__(self, reference: ReferenceConfig, dubbo: Optional[Dubbo] = None):
        self._initialized = False
        self._global_lock = threading.RLock()

        self._dubbo = dubbo or Dubbo()
        self._reference = reference

        self._url: Optional[URL] = None
        self._protocol: Optional[Protocol] = None
        self._invoker: Optional[Invoker] = None

        # initialize the invoker
        self._initialize()

    def _initialize(self):
        """
        Initialize the invoker.
        """
        with self._global_lock:
            if self._initialized:
                return

            # get the protocol
            protocol = extensionLoader.get_extension(
                Protocol, self._reference.protocol
            )()

            registry_config = self._dubbo.registry_config

            self._protocol = (
                RegistryProtocol(registry_config, protocol)
                if self._dubbo.registry_config
                else protocol
            )

            # build url
            reference_url = self._reference.to_url()
            if registry_config:
                self._url = registry_config.to_url().copy()
                self._url.path = reference_url.path
                for k, v in reference_url.parameters.items():
                    self._url.parameters[k] = v
            else:
                self._url = reference_url

            # create invoker
            self._invoker = self._protocol.refer(self._url)

            self._initialized = True

    def unary(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            UnaryCallType,
            method_name,
            request_serializer,
            response_deserializer,
        )

    def client_stream(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            ClientStreamCallType,
            method_name,
            request_serializer,
            response_deserializer,
        )

    def server_stream(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            ServerStreamCallType,
            method_name,
            request_serializer,
            response_deserializer,
        )

    def bidi_stream(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            BiStreamCallType,
            method_name,
            request_serializer,
            response_deserializer,
        )

    def _callable(
        self,
        call_type: CallType,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Generate a proxy for the given method
        :param call_type: The call type.
        :type call_type: str
        :param method_name: The method name.
        :type method_name: str
        :param request_serializer: The request serializer.
        :type request_serializer: Optional[SerializingFunction]
        :param response_deserializer: The response deserializer.
        :type response_deserializer: Optional[DeserializingFunction]
        :return: The proxy.
        :rtype: RpcCallable
        """
        # get invoker
        url = self._invoker.get_url()

        # clone url
        url = url.copy()
        url.parameters[common_constants.METHOD_KEY] = method_name
        # set call type
        url.attributes[common_constants.CALL_KEY] = call_type

        # set serializer and deserializer
        url.attributes[common_constants.SERIALIZER_KEY] = request_serializer
        url.attributes[common_constants.DESERIALIZER_KEY] = response_deserializer

        # create proxy
        return MultipleRpcCallable(self._invoker, url)
