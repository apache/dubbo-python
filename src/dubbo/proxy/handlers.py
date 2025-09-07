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
from typing import Any, Callable, Optional, get_type_hints

from dubbo.classes import MethodDescriptor
from dubbo.codec import DubboSerializationService
from dubbo.types import (
    DeserializingFunction,
    RpcTypes,
    SerializingFunction,
)

__all__ = ["RpcMethodHandler", "RpcServiceHandler"]


class RpcMethodConfigurationError(Exception):
    """
    Raised when an RPC method is configured incorrectly.
    """

    pass


class RpcMethodHandler:
    """
    Rpc method handler that wraps metadata and serialization logic for a callable.
    """

    __slots__ = ["_method_descriptor"]

    def __init__(self, method_descriptor: MethodDescriptor):
        """
        Initialize the RpcMethodHandler
        :param method_descriptor: the method descriptor
        :type method_descriptor: MethodDescriptor
        """
        self._method_descriptor = method_descriptor

    @property
    def method_descriptor(self) -> MethodDescriptor:
        """
        Get the method descriptor
        :return: the method descriptor
        :rtype: MethodDescriptor
        """
        return self._method_descriptor

    @staticmethod
    def get_codec(**kwargs) -> tuple:
        """
        Get serialization and deserialization functions
        :param kwargs: codec configuration like transport_type, parameter_types, return_type
        :return: serializer and deserializer functions
        :rtype: Tuple[SerializingFunction, DeserializingFunction]
        """
        return DubboSerializationService.create_serialization_functions(**kwargs)

    @classmethod
    def _infer_types_from_method(cls, method: Callable) -> tuple:
        """
        Infer method name, parameter types, and return type
        :param method: the callable method
        :type method: Callable
        :return: tuple(method_name, param_types, return_type)
        """
        try:
            type_hints = get_type_hints(method)
            sig = inspect.signature(method)
            method_name = method.__name__
            params = list(sig.parameters.values())

            # Detect unbound methods
            if params and params[0].name == "self":
                raise RpcMethodConfigurationError(
                    f"Method '{method_name}' appears unbound with 'self'. Pass a bound method or standalone function."
                )

            params_types = [type_hints.get(p.name, Any) for p in params]
            return_type = type_hints.get("return", Any)
            return method_name, params_types, return_type
        except RpcMethodConfigurationError:
            raise
        except Exception:
            return method.__name__, [Any], Any

    @classmethod
    def _create_method_descriptor(
        cls,
        method: Callable,
        method_name: str,
        params_types: list[type],
        return_type: type,
        rpc_type: str,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> MethodDescriptor:
        """
        Create a MethodDescriptor with serialization configuration
        :param method: callable method
        :param method_name: RPC method name
        :param params_types: parameter types
        :param return_type: return type
        :param rpc_type: RPC type (unary, client_stream, server_stream, bi_stream)
        :param codec: serialization codec
        :param request_deserializer: request deserialization function
        :param response_serializer: response serialization function
        :param kwargs: additional codec arguments
        :return: MethodDescriptor instance
        :rtype: MethodDescriptor
        """
        if request_deserializer is None or response_serializer is None:
            codec_kwargs = {
                "transport_type": codec,
                "parameter_types": params_types,
                "return_type": return_type,
                **kwargs,
            }
            serializer, deserializer = cls.get_codec(**codec_kwargs)
            request_deserializer = request_deserializer or deserializer
            response_serializer = response_serializer or serializer

        return MethodDescriptor(
            callable_method=method,
            method_name=method_name or method.__name__,
            arg_serialization=(None, request_deserializer),
            return_serialization=(response_serializer, None),
            rpc_type=rpc_type,
        )

    @classmethod
    def unary(
        cls,
        method: Callable,
        method_name: Optional[str] = None,
        params_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        """
        Create a unary method handler
        """
        name, param_types, ret_type = cls._infer_types_from_method(method)
        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=method_name or name,
                params_types=params_types or param_types,
                return_type=return_type or ret_type,
                rpc_type=RpcTypes.UNARY.value,
                codec=codec or "json",
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
                **kwargs,
            )
        )

    @classmethod
    def client_stream(
        cls,
        method: Callable,
        method_name: Optional[str] = None,
        params_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        """
        Create a client-streaming method handler
        """
        name, param_types, ret_type = cls._infer_types_from_method(method)
        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=method_name or name,
                params_types=params_types or param_types,
                return_type=return_type or ret_type,
                rpc_type=RpcTypes.CLIENT_STREAM.value,
                codec=codec or "json",
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
                **kwargs,
            )
        )

    @classmethod
    def server_stream(
        cls,
        method: Callable,
        method_name: Optional[str] = None,
        params_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        """
        Create a server-streaming method handler
        """
        name, param_types, ret_type = cls._infer_types_from_method(method)
        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=method_name or name,
                params_types=params_types or param_types,
                return_type=return_type or ret_type,
                rpc_type=RpcTypes.SERVER_STREAM.value,
                codec=codec or "json",
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
                **kwargs,
            )
        )

    @classmethod
    def bi_stream(
        cls,
        method: Callable,
        method_name: Optional[str] = None,
        params_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        """
        Create a bidirectional-streaming method handler
        """
        name, param_types, ret_type = cls._infer_types_from_method(method)
        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=method_name or name,
                params_types=params_types or param_types,
                return_type=return_type or ret_type,
                rpc_type=RpcTypes.BI_STREAM.value,
                codec=codec or "json",
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
                **kwargs,
            )
        )


class RpcServiceHandler:
    """
    Rpc service handler that maps method names to their corresponding RpcMethodHandler
    """

    __slots__ = ["_service_name", "_method_handlers"]

    def __init__(self, service_name: str, method_handlers: list[RpcMethodHandler]):
        """
        Initialize the RpcServiceHandler
        :param service_name: the name of the service
        :type service_name: str
        :param method_handlers: the list of RPC method handlers
        :type method_handlers: list[RpcMethodHandler]
        """
        self._service_name = service_name
        self._method_handlers: dict[str, RpcMethodHandler] = {}

        for method_handler in method_handlers:
            method_name = method_handler.method_descriptor.get_method_name()
            self._method_handlers[method_name] = method_handler

    @property
    def service_name(self) -> str:
        """
        Get the service name
        :return: the service name
        :rtype: str
        """
        return self._service_name

    @property
    def method_handlers(self) -> dict[str, RpcMethodHandler]:
        """
        Get the registered method handlers
        :return: method handlers dictionary
        :rtype: dict[str, RpcMethodHandler]
        """
        return self._method_handlers
