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

from dubbo.classes import SingletonBase
from dubbo.serialization import Deserializer, Serializer, ensure_bytes

__all__ = ["DirectSerializer", "DirectDeserializer"]


class DirectSerializer(Serializer, SingletonBase):
    """
    Direct serializer that does not perform any serialization. This serializer only checks if the given object is of
    type bytes, bytearray, or memoryview and ensures it is returned as a bytes object. If the object is not of the
    expected types, a SerializationError is raised. This serializer is a singleton.
    """

    def serialize(self, obj: Any) -> bytes:
        """
        Serialize an object to bytes.
        :param obj: The object to serialize.
        :type obj: Any
        :return: The serialized bytes.
        :rtype: bytes
        :raises SerializationError: If the object is not of type bytes, bytearray, or memoryview.
        """
        return ensure_bytes(obj) if obj is not None else b""


class DirectDeserializer(Deserializer):
    """
    Direct deserializer that does not perform any serialization. This deserializer only returns the given bytes object
    """

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize bytes to an object.
        :param data: The bytes to deserialize.
        :type data: bytes
        :return: The deserialized object.
        :rtype: Any
        :raises SerializationError: If the object is not of type bytes, bytearray, or memoryview.
        """
        return data
