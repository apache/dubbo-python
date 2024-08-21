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

from typing import Callable, Dict, Optional

from dubbo.types import (
    BiStreamCallType,
    CallType,
    ClientStreamCallType,
    DeserializingFunction,
    SerializingFunction,
    ServerStreamCallType,
    UnaryCallType,
)

__all__ = ["RpcMethodHandler", "RpcServiceHandler"]


class RpcMethodHandler:
    """
    Rpc method handler
    """

    def __init__(
        self,
        call_type: CallType,
        behavior: Callable,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
    ):
        """
        Initialize the RpcMethodHandler
        :param call_type: the call type.
        :type call_type: CallType
        :param behavior: the behavior of the method.
        :type behavior: Callable
        :param request_deserializer: the request deserializer.
        :type request_deserializer: Optional[DeserializingFunction]
        :param response_serializer: the response serializer.
        :type response_serializer: Optional[SerializingFunction]
        """
        self.call_type = call_type
        self.behavior = behavior
        self.request_deserializer = request_deserializer
        self.response_serializer = response_serializer

    @classmethod
    def unary(
        cls,
        behavior: Callable,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
    ):
        """
        Create a unary method handler
        """
        return cls(
            UnaryCallType,
            behavior,
            request_deserializer,
            response_serializer,
        )

    @classmethod
    def client_stream(
        cls,
        behavior: Callable,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
    ):
        """
        Create a client stream method handler
        """
        return cls(
            ClientStreamCallType,
            behavior,
            request_deserializer,
            response_serializer,
        )

    @classmethod
    def server_stream(
        cls,
        behavior: Callable,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
    ):
        """
        Create a server stream method handler
        """
        return cls(
            ServerStreamCallType,
            behavior,
            request_deserializer,
            response_serializer,
        )

    @classmethod
    def bi_stream(
        cls,
        behavior: Callable,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
    ):
        """
        Create a bidi stream method handler
        """
        return cls(
            BiStreamCallType,
            behavior,
            request_deserializer,
            response_serializer,
        )


class RpcServiceHandler:
    """
    Rpc service handler
    """

    def __init__(self, service_name: str, method_handlers: Dict[str, RpcMethodHandler]):
        """
        Initialize the RpcServiceHandler
        :param service_name: the name of the service.
        :type service_name: str
        :param method_handlers: the method handlers.
        :type method_handlers: Dict[str, RpcMethodHandler]
        """
        self.service_name = service_name
        self.method_handlers = method_handlers
