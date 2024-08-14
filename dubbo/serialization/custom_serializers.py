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

from typing import Any

from dubbo.serialization import (
    Deserializer,
    SerializationError,
    Serializer,
    ensure_bytes,
)
from dubbo.types import DeserializingFunction, SerializingFunction

__all__ = ["CustomSerializer", "CustomDeserializer"]


class CustomSerializer(Serializer):
    """
    Custom serializer that uses a custom serializing function to serialize objects.
    """

    __slots__ = ["serializer"]

    def __init__(self, serializer: SerializingFunction):
        self.serializer = serializer

    def serialize(self, obj: Any) -> bytes:
        """
        Serialize an object to bytes.
        :param obj: The object to serialize.
        :type obj: Any
        :return: The serialized bytes.
        :rtype: bytes
        :raises SerializationError: If the object is not of type bytes, bytearray, or memoryview.
        """
        try:
            serialized_obj = self.serializer(obj)
        except Exception as e:
            raise SerializationError(
                f"SerializationError: Failed to serialize object. Please check the serializer. \nDetails: {str(e)}",
            )

        return ensure_bytes(serialized_obj)


class CustomDeserializer(Deserializer):
    """
    Custom deserializer that uses a custom deserializing function to deserialize objects.
    """

    __slots__ = ["deserializer"]

    def __init__(self, deserializer: DeserializingFunction):
        self.deserializer = deserializer

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize bytes to an object.
        :param data: The bytes to deserialize.
        :type data: bytes
        :return: The deserialized object.
        :rtype: Any
        :raises SerializationError: If the object is not of type bytes, bytearray, or memoryview.
        """
        try:
            deserialized_obj = self.deserializer(data)
        except Exception as e:
            raise SerializationError(
                f"SerializationError: Failed to deserialize object. Please check the deserializer. \nDetails: {str(e)}",
            )

        return deserialized_obj
