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
from typing import Callable, Optional, List, Type, Any, get_type_hints
from dubbo.classes import MethodDescriptor
from dubbo.codec import DubboTransportService
from dubbo.types import (
    DeserializingFunction,
    RpcTypes,
    SerializingFunction,
)

__all__ = ["RpcMethodHandler", "RpcServiceHandler"]


class RpcMethodHandler:
    __slots__ = ["_method_descriptor"]

    def __init__(self, method_descriptor: MethodDescriptor):
        self._method_descriptor = method_descriptor

    @property
    def method_descriptor(self) -> MethodDescriptor:
        return self._method_descriptor

    @staticmethod
    def get_codec(**kwargs) -> tuple:
        return DubboTransportService.create_serialization_functions(**kwargs)

    @classmethod
    def _infer_types_from_method(cls, method: Callable) -> tuple:
        try:
            type_hints = get_type_hints(method)
            sig = inspect.signature(method)
            method_name = method.__name__
            params = list(sig.parameters.values())
            if params and params[0].name == "self":
                params = params[1:]

            params_types = [type_hints.get(p.name, Any) for p in params]
            return_type = type_hints.get("return", Any)
            return method_name, params_types, return_type
        except Exception:
            return method.__name__, [Any], Any

    @classmethod
    def _create_method_descriptor(
        cls,
        method: Callable,
        method_name: str,
        params_types: List[Type],
        return_type: Type,
        rpc_type: str,
        codec: Optional[str] = None,
        param_encoder: Optional[DeserializingFunction] = None,
        return_decoder: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> MethodDescriptor:
        if param_encoder is None or return_decoder is None:
            codec_kwargs = {
                "transport_type": codec or "json",
                "parameter_types": params_types,
                "return_type": return_type,
                **kwargs,
            }
            serializer, deserializer = cls.get_codec(**codec_kwargs)
            request_deserializer = param_encoder or deserializer
            response_serializer = return_decoder or serializer

        return MethodDescriptor(
            callable_method=method,
            method_name=method_name or method.__name__,
            arg_serialization=(None, request_deserializer),
            return_serialization=(response_serializer, None),
            rpc_type=rpc_type
        )

    @classmethod
    def unary(
        cls,
        method: Callable,
        method_name: Optional[str] = None,
        params_types: Optional[List[Type]] = None,
        return_type: Optional[Type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        inferred_name, inferred_param_types, inferred_return_type = cls._infer_types_from_method(method)
        resolved_method_name = method_name or inferred_name
        resolved_param_types = params_types or inferred_param_types
        resolved_return_type = return_type or inferred_return_type
        codec = codec or "json"

        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=resolved_method_name,
                params_types=resolved_param_types,
                return_type=resolved_return_type,
                rpc_type=RpcTypes.UNARY.value,
                codec=codec,
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
        params_types: Optional[List[Type]] = None,
        return_type: Optional[Type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        inferred_name, inferred_param_types, inferred_return_type = cls._infer_types_from_method(method)
        resolved_method_name = method_name or inferred_name
        resolved_param_types = params_types or inferred_param_types
        resolved_return_type = return_type or inferred_return_type
        resolved_codec = codec or "json"

        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=resolved_method_name,
                params_types=resolved_param_types,
                return_type=resolved_return_type,
                rpc_type=RpcTypes.CLIENT_STREAM.value,
                codec=resolved_codec,
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
        params_types: Optional[List[Type]] = None,
        return_type: Optional[Type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        inferred_name, inferred_param_types, inferred_return_type = cls._infer_types_from_method(method)
        resolved_method_name = method_name or inferred_name
        resolved_param_types = params_types or inferred_param_types
        resolved_return_type = return_type or inferred_return_type
        resolved_codec = codec or "json"

        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=resolved_method_name,
                params_types=resolved_param_types,
                return_type=resolved_return_type,
                rpc_type=RpcTypes.SERVER_STREAM.value,
                codec=resolved_codec,
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
        params_types: Optional[List[Type]] = None,
        return_type: Optional[Type] = None,
        codec: Optional[str] = None,
        request_deserializer: Optional[DeserializingFunction] = None,
        response_serializer: Optional[SerializingFunction] = None,
        **kwargs,
    ) -> "RpcMethodHandler":
        inferred_name, inferred_param_types, inferred_return_type = cls._infer_types_from_method(method)
        resolved_method_name = method_name or inferred_name
        resolved_param_types = params_types or inferred_param_types
        resolved_return_type = return_type or inferred_return_type
        resolved_codec = codec or "json"

        return cls(
            cls._create_method_descriptor(
                method=method,
                method_name=resolved_method_name,
                params_types=resolved_param_types,
                return_type=resolved_return_type,
                rpc_type=RpcTypes.BI_STREAM.value,
                codec=resolved_codec,
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
                **kwargs,
            )
        )


class RpcServiceHandler:
    __slots__ = ["_service_name", "_method_handlers"]

    def __init__(self, service_name: str, method_handlers: list[RpcMethodHandler]):
        self._service_name = service_name
        self._method_handlers: dict[str, RpcMethodHandler] = {}

        for method_handler in method_handlers:
            method_name = method_handler.method_descriptor.get_method_name()
            self._method_handlers[method_name] = method_handler

    @property
    def service_name(self) -> str:
        return self._service_name

    @property
    def method_handlers(self) -> dict[str, RpcMethodHandler]:
        return self._method_handlers