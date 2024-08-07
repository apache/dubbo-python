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

from dubbo.common import constants as common_constants
from dubbo.common.types import DeserializingFunction, SerializingFunction
from dubbo.config import ReferenceConfig
from dubbo.proxy import RpcCallable
from dubbo.proxy.callables import MultipleRpcCallable


class Client:

    __slots__ = ["_reference"]

    def __init__(self, reference: ReferenceConfig):
        self._reference = reference

    def unary(
        self,
        method_name: str,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ) -> RpcCallable:
        return self._callable(
            common_constants.UNARY_CALL_VALUE,
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
            common_constants.CLIENT_STREAM_CALL_VALUE,
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
            common_constants.SERVER_STREAM_CALL_VALUE,
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
            common_constants.BI_STREAM_CALL_VALUE,
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
        invoker = self._reference.get_invoker()
        url = invoker.get_url()

        # clone url
        url = url.copy()
        url.parameters[common_constants.METHOD_KEY] = method_name
        url.parameters[common_constants.CALL_KEY] = call_type

        # set serializer and deserializer
        url.attributes[common_constants.SERIALIZER_KEY] = request_serializer
        url.attributes[common_constants.DESERIALIZER_KEY] = response_deserializer

        # create proxy
        return MultipleRpcCallable(invoker, url)
