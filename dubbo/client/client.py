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
from typing import Optional

from dubbo.callable import RpcCallable
from dubbo.config import ConsumerConfig, ReferenceConfig
from dubbo.constants import common_constants
from dubbo.constants.type_constants import DeserializingFunction, SerializingFunction
from dubbo.logger.logger_factory import loggerFactory
from dubbo.serialization import Serialization

logger = loggerFactory.get_logger(__name__)


class Client:

    __slots__ = ["_consumer", "_reference"]

    def __init__(
        self, reference: ReferenceConfig, consumer: Optional[ConsumerConfig] = None
    ):
        self._reference = reference
        self._consumer = consumer or ConsumerConfig.default_config()

    def unary(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            common_constants.CALL_UNARY,
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
            common_constants.CALL_CLIENT_STREAM,
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
            common_constants.CALL_SERVER_STREAM,
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
            common_constants.CALL_BIDI_STREAM,
            method_name,
            request_serializer,
            response_deserializer,
        )

    def _callable(
        self,
        call_type: str,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        """
        Generate a callable for the given method
        Args:
            call_type: call type
            method_name: method name
            request_serializer: request serializer, args: Any, return: bytes
            response_deserializer: response deserializer, args: bytes, return: Any
        Returns:
            RpcCallable: The callable object
        """
        # get invoker
        invoker = self._reference.get_invoker()
        url = invoker.get_url()

        # clone url
        url = url.clone_without_attributes()
        url.add_parameter(common_constants.METHOD_KEY, method_name)
        url.add_parameter(common_constants.CALL_KEY, call_type)

        serialization = Serialization(request_serializer, response_deserializer)
        url.attributes[common_constants.SERIALIZATION] = serialization

        # create callable
        return RpcCallable(invoker, url)
