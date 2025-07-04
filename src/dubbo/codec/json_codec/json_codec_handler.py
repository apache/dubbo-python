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

from typing import Any, Type, List, Union, Dict, TypeVar, Protocol
from datetime import datetime, date, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import json

from .json_type import (
    TypeProviderFactory, SerializationState,
    SerializationException, DeserializationException
)

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

try:
    import ujson
    HAS_UJSON = True
except ImportError:
    HAS_UJSON = False

try:
    from pydantic import BaseModel, create_model
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


class EncodingFunction(Protocol):
    def __call__(self, obj: Any) -> bytes: ...


class DecodingFunction(Protocol):
    def __call__(self, data: bytes) -> Any: ...


ModelT = TypeVar('ModelT', bound=BaseModel)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return {
                "__datetime__": obj.isoformat(),
                "__timezone__": str(obj.tzinfo) if obj.tzinfo else None
            }
        elif isinstance(obj, date):
            return {"__date__": obj.isoformat()}
        elif isinstance(obj, time):
            return {"__time__": obj.isoformat()}
        elif isinstance(obj, Decimal):
            return {"__decimal__": str(obj)}
        elif isinstance(obj, (set, frozenset)):
            return {
                "__frozenset__" if isinstance(obj, frozenset) else "__set__": list(obj)
            }
        elif isinstance(obj, UUID):
            return {"__uuid__": str(obj)}
        elif isinstance(obj, Path):
            return {"__path__": str(obj)}
        else:
            return {"__fallback_string__": str(obj), "__original_type__": type(obj).__name__}


class JsonTransportEncoder:
    def __init__(self, parameter_types: List[Type] = None, maximum_depth: int = 100,
                 strict_validation: bool = True, **kwargs):
        self.parameter_types = parameter_types or []
        self.maximum_depth = maximum_depth
        self.strict_validation = strict_validation
        self.type_registry = TypeProviderFactory.create_default_registry()
        self.custom_encoder = CustomJSONEncoder(ensure_ascii=False, separators=(',', ':'))
        self.single_parameter_mode = len(self.parameter_types) == 1
        self.multiple_parameter_mode = len(self.parameter_types) > 1
        if self.multiple_parameter_mode and HAS_PYDANTIC:
            self.parameter_wrapper_model = self._create_parameter_wrapper_model()

    def _create_parameter_wrapper_model(self) -> Type[BaseModel]:
        model_fields = {}
        for i, param_type in enumerate(self.parameter_types):
            model_fields[f"parameter_{i}"] = (param_type, ...)
        return create_model('MethodParametersWrapper', **model_fields)

    def register_type_provider(self, provider) -> None:
        self.type_registry.register_provider(provider)

    def encode(self, arguments: tuple) -> bytes:
        try:
            if not arguments:
                return self._serialize_to_json_bytes([])

            if self.single_parameter_mode:
                parameter = arguments[0]
                serialized_param = self._serialize_with_state(parameter)
                if HAS_PYDANTIC and isinstance(parameter, BaseModel):
                    if hasattr(parameter, 'model_dump'):
                        return self._serialize_to_json_bytes(parameter.model_dump())
                    return self._serialize_to_json_bytes(parameter.dict())
                elif isinstance(parameter, dict):
                    return self._serialize_to_json_bytes(serialized_param)
                else:
                    return self._serialize_to_json_bytes(serialized_param)

            elif self.multiple_parameter_mode and HAS_PYDANTIC:
                wrapper_data = {f"parameter_{i}": arg for i, arg in enumerate(arguments)}
                wrapper_instance = self.parameter_wrapper_model(**wrapper_data)
                return self._serialize_to_json_bytes(wrapper_instance.model_dump())

            else:
                serialized_args = [self._serialize_with_state(arg) for arg in arguments]
                return self._serialize_to_json_bytes(serialized_args)

        except Exception as e:
            raise SerializationException(f"Encoding failed: {e}") from e

    def _serialize_with_state(self, obj: Any) -> Any:
        state = SerializationState(maximum_depth=self.maximum_depth)
        return self._serialize_recursively(obj, state)

    def _serialize_recursively(self, obj: Any, state: SerializationState) -> Any:
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, (list, tuple)):
            state.validate_circular_reference(obj)
            new_state = state.create_child_state(obj)
            return [self._serialize_recursively(item, new_state) for item in obj]
        elif isinstance(obj, dict):
            state.validate_circular_reference(obj)
            new_state = state.create_child_state(obj)
            result = {}
            for key, value in obj.items():
                if not isinstance(key, str):
                    if self.strict_validation:
                        raise SerializationException(f"Dictionary key must be string, got {type(key).__name__}")
                    key = str(key)
                result[key] = self._serialize_recursively(value, new_state)
            return result

        provider = self.type_registry.find_provider_for_object(obj)
        if provider:
            try:
                serialized = provider.serialize_to_dict(obj, state)
                return self._serialize_recursively(serialized, state)
            except Exception as e:
                if self.strict_validation:
                    raise SerializationException(f"Provider failed for {type(obj).__name__}: {e}") from e
                return {"__serialization_error__": str(e), "__original_type__": type(obj).__name__}
        else:
            if self.strict_validation:
                raise SerializationException(f"No provider for type {type(obj).__name__}")
            return {"__fallback_string__": str(obj), "__original_type__": type(obj).__name__}

    def _serialize_to_json_bytes(self, obj: Any) -> bytes:
        if HAS_ORJSON:
            try:
                return orjson.dumps(obj, default=self._orjson_default_handler)
            except TypeError:
                pass
        if HAS_UJSON:
            try:
                return ujson.dumps(obj, ensure_ascii=False, default=self._ujson_default_handler).encode('utf-8')
            except (TypeError, ValueError):
                pass
        return self.custom_encoder.encode(obj).encode('utf-8')

    def _orjson_default_handler(self, obj):
        if isinstance(obj, datetime):
            return {
                "__datetime__": obj.isoformat(),
                "__timezone__": str(obj.tzinfo) if obj.tzinfo else None
            }
        elif isinstance(obj, date):
            return {"__date__": obj.isoformat()}
        elif isinstance(obj, time):
            return {"__time__": obj.isoformat()}
        elif isinstance(obj, Decimal):
            return {"__decimal__": str(obj)}
        elif isinstance(obj, (set, frozenset)):
            return {
                "__frozenset__" if isinstance(obj, frozenset) else "__set__": list(obj)
            }
        elif isinstance(obj, UUID):
            return {"__uuid__": str(obj)}
        elif isinstance(obj, Path):
            return {"__path__": str(obj)}
        else:
            return {"__fallback_string__": str(obj), "__original_type__": type(obj).__name__}

    def _ujson_default_handler(self, obj):
        return self._orjson_default_handler(obj)


class JsonTransportDecoder:
    def __init__(self, target_type: Union[Type, List[Type]] = None, **kwargs):
        self.target_type = target_type
        if isinstance(target_type, list):
            self.multiple_parameter_mode = len(target_type) > 1
            self.parameter_types = target_type
            if self.multiple_parameter_mode and HAS_PYDANTIC:
                self.parameter_wrapper_model = self._create_parameter_wrapper_model()
        else:
            self.multiple_parameter_mode = False
            self.parameter_types = [target_type] if target_type else []

    def _create_parameter_wrapper_model(self) -> Type[BaseModel]:
        model_fields = {}
        for i, param_type in enumerate(self.parameter_types):
            model_fields[f"parameter_{i}"] = (param_type, ...)
        return create_model('MethodParametersWrapper', **model_fields)

    def decode(self, data: bytes) -> Any:
        try:
            if not data:
                return None
            json_data = self._deserialize_from_json_bytes(data)
            reconstructed_data = self._reconstruct_objects(json_data)
            if not self.target_type:
                return reconstructed_data
            if isinstance(self.target_type, list):
                if self.multiple_parameter_mode and HAS_PYDANTIC:
                    wrapper_instance = self.parameter_wrapper_model(**reconstructed_data)
                    return tuple(getattr(wrapper_instance, f"parameter_{i}") for i in range(len(self.parameter_types)))
                else:
                    return self._decode_to_target_type(reconstructed_data, self.parameter_types[0])
            else:
                return self._decode_to_target_type(reconstructed_data, self.target_type)
        except Exception as e:
            raise DeserializationException(f"Decoding failed: {e}") from e

    def _deserialize_from_json_bytes(self, data: bytes) -> Any:
        if HAS_ORJSON:
            try:
                return orjson.loads(data)
            except orjson.JSONDecodeError:
                pass
        if HAS_UJSON:
            try:
                return ujson.loads(data.decode('utf-8'))
            except (ujson.JSONDecodeError, UnicodeDecodeError):
                pass
        return json.loads(data.decode('utf-8'))

    def _decode_to_target_type(self, json_data: Any, target_type: Type) -> Any:
        if target_type in (str, int, float, bool, list, dict):
            return target_type(json_data)
        return json_data

    def _reconstruct_objects(self, data: Any) -> Any:
        if not isinstance(data, dict):
            if isinstance(data, list):
                return [self._reconstruct_objects(item) for item in data]
            return data
        if "__datetime__" in data:
            return datetime.fromisoformat(data["__datetime__"])
        elif "__date__" in data:
            return date.fromisoformat(data["__date__"])
        elif "__time__" in data:
            return time.fromisoformat(data["__time__"])
        elif "__decimal__" in data:
            return Decimal(data["__decimal__"])
        elif "__set__" in data:
            return set(self._reconstruct_objects(item) for item in data["__set__"])
        elif "__frozenset__" in data:
            return frozenset(self._reconstruct_objects(item) for item in data["__frozenset__"])
        elif "__uuid__" in data:
            return UUID(data["__uuid__"])
        elif "__path__" in data:
            return Path(data["__path__"])
        elif "__dataclass__" in data or "__pydantic_model__" in data:
            return data
        else:
            return {key: self._reconstruct_objects(value) for key, value in data.items()}


class JsonTransportCodec:
    def __init__(self, parameter_types: List[Type] = None, return_type: Type = None,
                 maximum_depth: int = 100, strict_validation: bool = True, **kwargs):
        self.parameter_types = parameter_types or []
        self.return_type = return_type
        self.maximum_depth = maximum_depth
        self.strict_validation = strict_validation
        self._encoder = JsonTransportEncoder(
            parameter_types=parameter_types,
            maximum_depth=maximum_depth,
            strict_validation=strict_validation,
            **kwargs
        )
        self._decoder = JsonTransportDecoder(target_type=return_type, **kwargs)

    def encode_parameters(self, *arguments) -> bytes:
        return self._encoder.encode(arguments)

    def decode_return_value(self, data: bytes) -> Any:
        return self._decoder.decode(data)

    def get_encoder(self) -> JsonTransportEncoder:
        return self._encoder

    def get_decoder(self) -> JsonTransportDecoder:
        return self._decoder

    def register_type_provider(self, provider) -> None:
        self._encoder.register_type_provider(provider)
