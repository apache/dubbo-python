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

from typing import Any, Optional

from ._interface import DeserializationException, ProtobufDecoder, ProtobufEncoder, SerializationException

try:
    from google.protobuf.message import Message as GoogleMessage

    HAS_PROTOC = True
except ImportError:
    HAS_PROTOC = False


class GoogleProtobufMessageHandler(ProtobufEncoder, ProtobufDecoder):
    """
    The Google protoc message handler for protobuf messages.
    """

    _SERIALIZATION_TYPE = "protoc"

    def __init__(self):
        if not HAS_PROTOC:
            raise ImportError("google.protobuf is required for GoogleProtobufMessageHandler")

    @classmethod
    def get_serialization_type(cls) -> str:
        return cls._SERIALIZATION_TYPE

    def can_handle(self, obj: Any, obj_type: Optional[type] = None) -> bool:
        if obj is not None and HAS_PROTOC and isinstance(obj, GoogleMessage):
            return True
        if obj_type is not None:
            return self._is_protoc_message(obj_type)
        return False

    def encode(self, obj: Any, obj_type: Optional[type] = None) -> bytes:
        try:
            if isinstance(obj, GoogleMessage):
                return obj.SerializeToString()

            if obj_type and self._is_protoc_message(obj_type):
                if isinstance(obj, obj_type):
                    return obj.SerializeToString()
                elif isinstance(obj, dict):
                    message = obj_type(**obj)
                    return message.SerializeToString()
                else:
                    raise SerializationException(f"Cannot convert {type(obj)} to {obj_type}")

            raise SerializationException(f"Cannot encode {type(obj)} as protoc message")
        except Exception as e:
            raise SerializationException(f"Protoc encoding failed: {e}") from e

    def decode(self, data: bytes, target_type: type) -> Any:
        try:
            if not self._is_protoc_message(target_type):
                raise DeserializationException(f"{target_type} is not a protoc message type")
            message = target_type()
            message.ParseFromString(data)
            return message
        except Exception as e:
            raise DeserializationException(f"Protoc decoding failed: {e}") from e

    def _is_protoc_message(self, obj_type: type) -> bool:
        try:
            return HAS_PROTOC and issubclass(obj_type, GoogleMessage)
        except (TypeError, AttributeError):
            return False
