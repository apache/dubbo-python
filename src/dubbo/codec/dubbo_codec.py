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

from typing import Any, Type, Optional, Callable, List, Dict
from dataclasses import dataclass
import inspect

from dubbo.classes import CodecHelper
from dubbo.codec.json_codec import JsonTransportCodec, JsonTransportEncoder, JsonTransportDecoder

@dataclass
class ParameterDescriptor:
    """Detailed information about a method parameter"""
    name: str
    annotation: Any
    is_required: bool = True
    default_value: Any = None


@dataclass
class MethodDescriptor:
    """Complete method descriptor with all necessary information"""
    function: Callable
    name: str
    parameters: List[ParameterDescriptor]
    return_parameter: ParameterDescriptor
    documentation: Optional[str] = None


class DubboTransportService:
    """Enhanced Dubbo transport service with robust type handling"""

    @staticmethod
    def create_transport_codec(transport_type: str = 'json', parameter_types: List[Type] = None,
                               return_type: Type = None, **codec_options):
        """Create transport codec with enhanced parameter structure"""
        if transport_type == 'json':
            return JsonTransportCodec(
                parameter_types=parameter_types,
                return_type=return_type,
                **codec_options
            )
        else:
            from dubbo.extension.extension_loader import ExtensionLoader
            Codec = CodecHelper.get_class()
            codec_class = ExtensionLoader().get_extension(Codec, transport_type)
            return codec_class(
                parameter_types=parameter_types,
                return_type=return_type,
                **codec_options
            )

    @staticmethod
    def create_encoder_decoder_pair(transport_type: str, parameter_types: List[Type] = None,
                                    return_type: Type = None, **codec_options) -> tuple[any,any]:
        """Create separate encoder and decoder instances"""

        if transport_type == 'json':
            parameter_encoder = JsonTransportEncoder(parameter_types=parameter_types, **codec_options)
            return_decoder = JsonTransportDecoder(target_type=return_type, **codec_options)
            return parameter_encoder, return_decoder
        else:
            from dubbo.extension.extension_loader import ExtensionLoader
            Codec = CodecHelper.get_class()
            codec_class = ExtensionLoader().get_extension(Codec, transport_type)

            codec_instance = codec_class(
                parameter_types=parameter_types,
                return_type=return_type,
                **codec_options
            )

            return codec_instance.get_encoder(), codec_instance.get_decoder()

    @staticmethod
    def create_serialization_functions(transport_type: str, parameter_types: List[Type] = None,
                                       return_type: Type = None, **codec_options) -> tuple[Callable, Callable]:
        """Create serializer and deserializer functions for RPC (backward compatibility)"""

        parameter_encoder, return_decoder = DubboTransportService.create_encoder_decoder_pair(
            transport_type=transport_type,
            parameter_types=parameter_types,
            return_type=return_type,
            **codec_options
        )

        def serialize_method_parameters(*args) -> bytes:
            return parameter_encoder.encode(args)

        def deserialize_method_return(data: bytes):
            return return_decoder.decode(data)
        
        print(type(serialize_method_parameters),type(deserialize_method_return))
        return serialize_method_parameters, deserialize_method_return

    @staticmethod
    def create_method_descriptor(func: Callable, method_name: str = None,
                                 parameter_types: List[Type] = None, return_type: Type = None,
                                 interface: Callable = None) -> MethodDescriptor:
        """Create a method descriptor from function and configuration"""

        name = method_name or (interface.__name__ if interface else func.__name__)
        sig = inspect.signature(interface if interface else func)

        parameters = []
        resolved_parameter_types = parameter_types or []

        for i, (param_name, param) in enumerate(sig.parameters.items()):
            if param_name == 'self':
                continue

            param_index = i - 1 if 'self' in sig.parameters else i

            if param_index < len(resolved_parameter_types):
                param_type = resolved_parameter_types[param_index]
            elif param.annotation != inspect.Parameter.empty:
                param_type = param.annotation
            else:
                param_type = Any

            is_required = param.default == inspect.Parameter.empty
            default_value = param.default if not is_required else None

            parameters.append(ParameterDescriptor(
                name=param_name,
                annotation=param_type,
                is_required=is_required,
                default_value=default_value
            ))

        if return_type:
            resolved_return_type = return_type
        elif sig.return_annotation != inspect.Signature.empty:
            resolved_return_type = sig.return_annotation
        else:
            resolved_return_type = Any

        return_parameter = ParameterDescriptor(
            name="return_value",
            annotation=resolved_return_type
        )

        return MethodDescriptor(
            function=func,
            name=name,
            parameters=parameters,
            return_parameter=return_parameter,
            documentation=func.__doc__
        )