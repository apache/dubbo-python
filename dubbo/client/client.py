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
from typing import Optional, Union

from dubbo.callable.rpc_callable import AsyncRpcCallable, RpcCallable
from dubbo.callable.rpc_callable_factory import DefaultRpcCallableFactory
from dubbo.common.constants import common_constants
from dubbo.common.constants.type_constants import (DeserializingFunction,
                                                   SerializingFunction)
from dubbo.common.url import URL
from dubbo.config import ConsumerConfig, ReferenceConfig
from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


class Client:

    _consumer: ConsumerConfig
    _reference: ReferenceConfig

    __slots__ = ["_consumer", "_reference"]

    def __init__(
        self, reference: ReferenceConfig, consumer: Optional[ConsumerConfig] = None
    ):
        self._reference = reference
        self._consumer = consumer or ConsumerConfig.default_config()

    def unary(
        self,
        method_name: str,
        req_serializer: Optional[SerializingFunction] = None,
        resp_deserializer: Optional[DeserializingFunction] = None,
    ) -> Union[RpcCallable, AsyncRpcCallable]:
        return self._callable(
            common_constants.CALL_UNARY, method_name, req_serializer, resp_deserializer
        )

    def client_stream(
        self,
        method_name: str,
        req_serializer: Optional[SerializingFunction] = None,
        resp_deserializer: Optional[DeserializingFunction] = None,
    ) -> Union[RpcCallable, AsyncRpcCallable]:
        return self._callable(
            common_constants.CALL_CLIENT_STREAM,
            method_name,
            req_serializer,
            resp_deserializer,
        )

    def server_stream(
        self,
        method_name: str,
        req_serializer: Optional[SerializingFunction] = None,
        resp_deserializer: Optional[DeserializingFunction] = None,
    ) -> Union[RpcCallable, AsyncRpcCallable]:
        return self._callable(
            common_constants.CALL_SERVER_STREAM,
            method_name,
            req_serializer,
            resp_deserializer,
        )

    def bidi_stream(
        self,
        method_name: str,
        req_serializer: Optional[SerializingFunction] = None,
        resp_deserializer: Optional[DeserializingFunction] = None,
    ) -> Union[RpcCallable, AsyncRpcCallable]:
        return self._callable(
            common_constants.CALL_BIDI_STREAM,
            method_name,
            req_serializer,
            resp_deserializer,
        )

    def _callable(
        self,
        call_type: str,
        method_name: str,
        req_serializer: Optional[SerializingFunction] = None,
        resp_deserializer: Optional[DeserializingFunction] = None,
    ) -> Union[RpcCallable, AsyncRpcCallable]:
        """
        Generate a callable for the given method
        Args:
            call_type: call type
            method_name: method name
            req_serializer: request serializer, args: Any, return: bytes
            resp_deserializer: response deserializer, args: bytes, return: Any
        Returns:
            RpcCallable: The callable object
        """
        # get invoker
        invoker = self._reference.get_invoker()
        url = invoker.get_url()

        method_url = URL(
            method_name,
            common_constants.LOCALHOST_KEY,
            parameters={
                common_constants.METHOD_KEY: method_name,
                common_constants.TYPE_CALL: call_type,
            },
        )
        # add attributes
        method_url.add_attribute(common_constants.SERIALIZATION, req_serializer)
        method_url.add_attribute(common_constants.DESERIALIZATION, resp_deserializer)

        # put the method url into the invoker url
        url.add_attribute(method_name, method_url)

        # create callable
        rpc_callable = DefaultRpcCallableFactory().get_proxy(invoker, url)

        return rpc_callable
