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

import json
from typing import Any, Optional

from ._interface import DeserializationException, ProtobufDecoder, ProtobufEncoder, SerializationException

__all__ = ["PrimitiveHandler"]


class PrimitiveHandler(ProtobufEncoder, ProtobufDecoder):
    """
    The primitive type handler for basic Python types.
    """

    _SERIALIZATION_TYPE = "primitive"

    @classmethod
    def get_serialization_type(cls) -> str:
        """
        Get serialization type of current implementation
        :return: The serialization type.
        :rtype: str
        """
        return cls._SERIALIZATION_TYPE

    def can_handle(self, obj: Any, obj_type: Optional[type] = None) -> bool:
        """
        Check if this handler can handle the given object/type
        :param obj: The object to check
        :param obj_type: The type to check
        :return: True if can handle, False otherwise
        :rtype: bool
        """
        if obj is not None:
            return isinstance(obj, (str, int, float, bool, bytes))
        if obj_type is not None:
            return obj_type in (str, int, float, bool, bytes)
        return False

    def encode(self, obj: Any, obj_type: Optional[type] = None) -> bytes:
        """
        Encode the primitive object to bytes.
        :param obj: The object to encode.
        :param obj_type: The type hint for encoding.
        :return: The encoded bytes.
        :rtype: bytes
        """
        try:
            if not isinstance(obj, (str, int, float, bool, bytes)):
                raise SerializationException(f"Cannot encode {type(obj)} as primitive")

            json_str = json.dumps({"value": obj, "type": type(obj).__name__})
            return json_str.encode("utf-8")
        except Exception as e:
            raise SerializationException(f"Primitive encoding failed: {e}") from e

    def decode(self, data: bytes, target_type: type) -> Any:
        """
        Decode the data to primitive object.
        :param data: The data to decode.
        :param target_type: The target primitive type.
        :return: The decoded object.
        :rtype: Any
        """
        try:
            if target_type not in (str, int, float, bool, bytes):
                raise DeserializationException(f"{target_type} is not a supported primitive type")

            json_str = data.decode("utf-8")
            parsed = json.loads(json_str)
            value = parsed.get("value")

            if target_type is str:
                return str(value)
            elif target_type is int:
                return int(value)
            elif target_type is float:
                return float(value)
            elif target_type is bool:
                return bool(value)
            elif target_type is bytes:
                if isinstance(value, bytes):
                    return value
                elif isinstance(value, list):
                    return bytes(value)
                else:
                    return str(value).encode()
            else:
                return value

        except Exception as e:
            raise DeserializationException(f"Primitive decoding failed: {e}") from e
