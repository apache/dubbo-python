#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
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
from dubbo.classes import MethodDescriptor
from dubbo.codec import DubboSerializationService
from dubbo.configs import ReferenceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Invoker, Protocol
from dubbo.proxy import RpcCallable, RpcCallableFactory
from dubbo.proxy.callables import DefaultRpcCallableFactory
from dubbo.registry.protocol import RegistryProtocol
from dubbo.types import (
    DeserializingFunction,
    RpcTypes,
    SerializingFunction,
)
from dubbo.url import URL

__all__ = ["Client"]


class Client:
    def __init__(self, reference: ReferenceConfig, dubbo: Optional[Dubbo] = None):
        self._initialized = False
        self._global_lock = threading.RLock()

        self._dubbo = dubbo or Dubbo()
        self._reference = reference

        self._url: Optional[URL] = None
        self._protocol: Optional[Protocol] = None
        self._invoker: Optional[Invoker] = None

        self._callable_factory: RpcCallableFactory = DefaultRpcCallableFactory()

        # initialize the invoker
        self._initialize()

    def _initialize(self):
        """
        Initialize the invoker with protocol and URL.
        """
        with self._global_lock:
            if self._initialized:
                return

            # get the protocol extension
            protocol = extensionLoader.get_extension(Protocol, self._reference.protocol)()

            registry_config = self._dubbo.registry_config
            self._protocol = RegistryProtocol(registry_config, protocol) if registry_config else protocol

            # build the reference URL
            reference_url = self._reference.to_url()
            if registry_config:
                self._url = registry_config.to_url().copy()
                self._url.path = reference_url.path
                for k, v in reference_url.parameters.items():
                    self._url.parameters[k] = v
            else:
                self._url = reference_url

            # create the invoker using the protocol
            self._invoker = self._protocol.refer(self._url)

            self._initialized = True

    def _create_rpc_callable(
        self,
        rpc_type: str,
        method_name: str,
        params_types: list[type],
        return_type: type,
        codec: Optional[str] = None,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Create an RPC callable with the specified type.

        :param rpc_type: Type of RPC (unary, client_stream, server_stream, bi_stream)
        :param method_name: Name of the method to call
        :param params_types: List of parameter types
        :param return_type: Return type of the method
        :param codec: Optional codec to use for serialization
        :param request_serializer: Optional custom request serializer
        :param response_deserializer: Optional custom response deserializer
        :return: RPC callable proxy
        :rtype: RpcCallable
        """
        # determine serializers
        if request_serializer and response_deserializer:
            req_ser = request_serializer
            res_deser = response_deserializer
        else:
            req_ser, res_deser = DubboSerializationService.create_serialization_functions(
                codec,
                parameter_types=params_types,
                return_type=return_type,
            )

        # create method descriptor
        descriptor = MethodDescriptor(
            method_name=method_name,
            arg_serialization=(req_ser, None),
            return_serialization=(None, res_deser),
            rpc_type=rpc_type,
        )

        return self._callable(descriptor)

    def unary(
        self,
        method_name: str,
        params_types: list[type],
        return_type: type,
        codec: Optional[str] = None,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Create a unary RPC callable.
        """
        return self._create_rpc_callable(
            rpc_type=RpcTypes.UNARY.value,
            method_name=method_name,
            params_types=params_types,
            return_type=return_type,
            codec=codec,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )

    def client_stream(
        self,
        method_name: str,
        params_types: list[type],
        return_type: type,
        codec: Optional[str] = None,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Create a client-streaming RPC callable.
        """
        return self._create_rpc_callable(
            rpc_type=RpcTypes.CLIENT_STREAM.value,
            method_name=method_name,
            params_types=params_types,
            return_type=return_type,
            codec=codec,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )

    def server_stream(
        self,
        method_name: str,
        params_types: list[type],
        return_type: type,
        codec: Optional[str] = None,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Create a server-streaming RPC callable.
        """
        return self._create_rpc_callable(
            rpc_type=RpcTypes.SERVER_STREAM.value,
            method_name=method_name,
            params_types=params_types,
            return_type=return_type,
            codec=codec,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )

    def bi_stream(
        self,
        method_name: str,
        params_types: list[type],
        return_type: type,
        codec: Optional[str] = None,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Create a bidirectional-streaming RPC callable.
        """
        return self._create_rpc_callable(
            rpc_type=RpcTypes.BI_STREAM.value,
            method_name=method_name,
            params_types=params_types,
            return_type=return_type,
            codec=codec,
            request_serializer=request_serializer,
            response_deserializer=response_deserializer,
        )

    def _callable(self, method_descriptor: MethodDescriptor) -> RpcCallable:
        """
        Generate a proxy for the given method.

        :param method_descriptor: The method descriptor.
        :return: The RPC callable proxy.
        :rtype: RpcCallable
        """
        # get invoker URL and clone it
        url = self._invoker.get_url().copy()
        url.parameters[common_constants.METHOD_KEY] = method_descriptor.get_method_name()
        url.attributes[common_constants.METHOD_DESCRIPTOR_KEY] = method_descriptor

        # create proxy callable
        return self._callable_factory.get_callable(self._invoker, url)
