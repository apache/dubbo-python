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

from typing import Any, Optional, get_args, get_origin, Union

from ._interfaces import JsonCodec, TypeHandler
from .orjson_codec import OrJsonCodec
from .standard_json import StandardJsonCodec
from .ujson_codec import UJsonCodec

__all__ = ["JsonTransportCodec", "SerializationException", "DeserializationException"]


class SerializationException(Exception):
    """Exception raised during serialization"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DeserializationException(Exception):
    """Exception raised during deserialization"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class JsonTransportCodec:
    """
    JSON Transport Codec with integrated encoder/decoder functionality.

    This class serves as both a transport codec and provides encoder/decoder
    interface compatibility for services that expect separate encoder/decoder objects.
    """

    def __init__(
        self,
        parameter_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        maximum_depth: int = 100,
        strict_validation: bool = True,
        **kwargs,
    ):
        """
        Initialize the JSON transport codec.

        :param parameter_types: list of parameter types for the method.
        :param return_type: Return type for the method.
        :param maximum_depth: Maximum serialization depth.
        :param strict_validation: Whether to use strict validation.
        """
        self.parameter_types = parameter_types or []
        self.return_type = return_type
        self.maximum_depth = maximum_depth
        self.strict_validation = strict_validation

        # Initialize codecs and handlers using the extension pattern
        self._json_codecs = self._setup_json_codecs()
        self._type_handlers = self._setup_type_handlers()

    def _setup_json_codecs(self) -> list[JsonCodec]:
        """
        Setup JSON codecs in priority order.
        """
        codecs = []

        # Try orjson first (fastest)
        orjson_codec = OrJsonCodec()
        if orjson_codec.can_handle(None):  # Check availability
            codecs.append(orjson_codec)

        # Try ujson second
        ujson_codec = UJsonCodec()
        if ujson_codec.can_handle(None):  # Check availability
            codecs.append(ujson_codec)

        # Always include standard json as fallback
        codecs.append(StandardJsonCodec())

        return codecs

    def _setup_type_handlers(self) -> list[TypeHandler]:
        """
        Setup type handlers for different object types.
        """
        handlers = []

        from dubbo.extension import extensionLoader

        handler_names = ["datetime", "pydantic", "decimal", "enum", "simple", "dataclass", "collection"]

        for name in handler_names:
            try:
                plugin_class = extensionLoader.get_extension(TypeHandler, name)
                if plugin_class:
                    plugin_instance = plugin_class()
                    handlers.append(plugin_instance)
            except Exception as e:
                print(f"Warning: Could not load type handler plugin '{name}': {e}")
        return handlers

    # Core encoding/decoding methods
    def encode_parameters(self, *arguments) -> bytes:
        """
        Encode parameters to JSON bytes.

        :param arguments: The arguments to encode.
        :return: Encoded JSON bytes.
        :rtype: bytes
        """
        try:
            if not arguments:
                return self._encode_with_codecs([])

            # Handle single parameter case
            if len(self.parameter_types) == 1:
                serialized = self._serialize_object(arguments[0])
                return self._encode_with_codecs(serialized)

            # Handle multiple parameters
            elif len(self.parameter_types) > 1:
                serialized_args = [self._serialize_object(arg) for arg in arguments]
                return self._encode_with_codecs(serialized_args)

            # No type constraints
            else:
                if len(arguments) == 1:
                    serialized = self._serialize_object(arguments[0])
                    return self._encode_with_codecs(serialized)
                else:
                    serialized_args = [self._serialize_object(arg) for arg in arguments]
                    return self._encode_with_codecs(serialized_args)

        except Exception as e:
            raise SerializationException(f"Parameter encoding failed: {e}") from e

    def decode_return_value(self, data: bytes) -> Any:
        """
        Decode return value from JSON bytes and validate against self.return_type.
        Supports nested generics and marker-wrapped types.
        """
        if not data:
            return None

        # Step 1: Decode JSON bytes to Python object
        json_data = self._decode_with_codecs(data)

        # Step 2: Reconstruct marker-based objects (datetime, UUID, set, frozenset, dataclass, pydantic)
        obj = self._reconstruct_objects(json_data)

        # Step 3: Validate type recursively
        if self.return_type:
            if not self._validate_type(obj, self.return_type):
                raise DeserializationException(
                    f"Decoded object type {type(obj).__name__} does not match expected {self.return_type}"
                )

        return obj

    def _validate_type(self, obj: Any, expected_type: type) -> bool:
        """
        Recursively validate obj against expected_type.
        Supports Union, List, Tuple, Set, frozenset, dataclass, Enum, Pydantic models.
        """
        origin = get_origin(expected_type)
        args = get_args(expected_type)

        # Handle Union types
        if origin is Union:
            return any(self._validate_type(obj, t) for t in args)

        # Handle container types
        if origin in (list, tuple, set, frozenset):
            if not isinstance(obj, origin):
                return False
            if args:
                return all(self._validate_type(item, args[0]) for item in obj)
            return True

        # Dataclass
        if hasattr(expected_type, "__dataclass_fields__"):
            return hasattr(obj, "__dataclass_fields__") and type(obj) == expected_type

        # Enum
        import enum

        if isinstance(expected_type, type) and issubclass(expected_type, enum.Enum):
            return isinstance(obj, expected_type)

        # Pydantic
        try:
            from pydantic import BaseModel

            if issubclass(expected_type, BaseModel):
                return isinstance(obj, expected_type)
        except Exception:
            pass

        # Plain types
        return isinstance(obj, expected_type)

    # Encoder/Decoder interface compatibility methods
    def encoder(self):
        """
        Get the parameter encoder instance (returns self for compatibility).

        :return: Self as encoder.
        :rtype: JsonTransportCodec
        """
        return self

    def decoder(self):
        """
        Get the return value decoder instance (returns self for compatibility).

        :return: Self as decoder.
        :rtype: JsonTransportCodec
        """
        return self

    def encode(self, arguments: tuple) -> bytes:
        """
        Encode method for encoder interface compatibility.

        :param arguments: The method arguments to encode.
        :type arguments: tuple
        :return: Encoded parameter bytes.
        :rtype: bytes
        """
        return self.encode_parameters(*arguments)

    def decode(self, data: bytes) -> Any:
        """
        Decode method for decoder interface compatibility.

        :param data: The bytes to decode.
        :type data: bytes
        :return: Decoded return value.
        :rtype: Any
        """
        return self.decode_return_value(data)

    # Internal serialization methods
    def _serialize_object(self, obj: Any, depth: int = 0) -> Any:
        """
        Serialize an object using the appropriate type handler.

        :param obj: The object to serialize.
        :param depth: Current serialization depth.
        :return: Serialized representation.
        """
        if depth > self.maximum_depth:
            raise SerializationException(f"Maximum depth {self.maximum_depth} exceeded")

        # Handle simple types
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj

        # Handle collections
        if isinstance(obj, (list, tuple)):
            return [self._serialize_object(item, depth + 1) for item in obj]

        elif isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if not isinstance(key, str):
                    if self.strict_validation:
                        raise SerializationException(f"Dictionary key must be string, got {type(key).__name__}")
                    key = str(key)
                result[key] = self._serialize_object(value, depth + 1)
            return result

        # Use type handlers for complex objects
        obj_type = type(obj)
        for handler in self._type_handlers:
            if handler.can_serialize_type(obj, obj_type):
                try:
                    serialized = handler.serialize_to_dict(obj)
                    return self._serialize_object(serialized, depth + 1)
                except Exception as e:
                    if self.strict_validation:
                        raise SerializationException(f"Handler failed for {type(obj).__name__}: {e}") from e
                    return {"$error": str(e), "$type": type(obj).__name__}

        # Fallback for unknown types
        if self.strict_validation:
            raise SerializationException(f"No handler for type {type(obj).__name__}")
        return {"$fallback": str(obj), "$type": type(obj).__name__}

    def _encode_with_codecs(self, obj: Any) -> bytes:
        """
        Encode object using the first available JSON codec.

        :param obj: The object to encode.
        :return: JSON bytes.
        :rtype: bytes
        """
        last_error = None

        for codec in self._json_codecs:
            try:
                return codec.encode(obj)
            except Exception as e:
                last_error = e
                continue

        raise SerializationException(f"All JSON codecs failed. Last error: {last_error}")

    def _decode_with_codecs(self, data: bytes) -> Any:
        """
        Decode JSON bytes using the first available codec.

        :param data: The JSON bytes to decode.
        :return: Decoded object.
        :rtype: Any
        """
        last_error = None

        for codec in self._json_codecs:
            try:
                return codec.decode(data)
            except Exception as e:
                last_error = e
                continue

        raise DeserializationException(f"All JSON codecs failed. Last error: {last_error}")

    def _reconstruct_objects(self, data: Any) -> Any:
        """
        Reconstruct objects from their serialized form.

        :param data: The data to reconstruct.
        :return: Reconstructed object.
        :rtype: Any
        """
        if not isinstance(data, dict):
            if isinstance(data, list):
                return [self._reconstruct_objects(item) for item in data]
            return data

        if "$date" in data:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(data["$date"].replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)

        elif "$uuid" in data:
            from uuid import UUID

            return UUID(data["$uuid"])

        elif "$set" in data:
            return set(self._reconstruct_objects(item) for item in data["$set"])

        elif "$frozenset" in data:
            return frozenset(self._reconstruct_objects(item) for item in data["$frozenset"])

        elif "$tuple" in data:
            return tuple(self._reconstruct_objects(item) for item in data["$tuple"])

        elif "$binary" in data:
            import base64

            binary_data = base64.b64decode(data["$binary"])
            return binary_data

        elif "$decimal" in data:
            from decimal import Decimal

            return Decimal(data["$decimal"])

        elif "$pydantic" in data and "$data" in data:
            return self._reconstruct_pydantic_model(data)

        elif "$dataclass" in data:
            return self._reconstruct_dataclass(data)

        elif "$enum" in data:
            return self._reconstruct_enum(data)

        else:
            return {key: self._reconstruct_objects(value) for key, value in data.items()}

    def _reconstruct_pydantic_model(self, data: dict) -> Any:
        """Reconstruct a Pydantic model from serialized data"""
        try:
            model_path = data.get("$pydantic") or data.get("__pydantic_model__")
            model_data = data.get("$data") or data.get("__model_data__")

            module_name, class_name = model_path.rsplit(".", 1)

            import importlib

            module = importlib.import_module(module_name)
            model_class = getattr(module, class_name)

            reconstructed_data = self._reconstruct_objects(model_data)
            return model_class(**reconstructed_data)
        except Exception:
            return self._reconstruct_objects(model_data or {})

    def _reconstruct_dataclass(self, data: dict) -> Any:
        """Reconstruct a dataclass from serialized data"""

        class_path = data.get("$dataclass") or data.get("__dataclass__")
        fields_data = data.get("$fields") or data.get("fields")

        module_name, class_name = class_path.rsplit(".", 1)

        import importlib

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)

        fields = self._reconstruct_objects(fields_data)
        return cls(**fields)

    def _reconstruct_enum(self, data: dict) -> Any:
        """Reconstruct an enum from serialized data"""

        enum_path = data.get("$enum") or data.get("__enum__")
        enum_value = data.get("$value") or data.get("value")

        module_name, class_name = enum_path.rsplit(".", 1)

        import importlib

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)

        return cls(enum_value)
