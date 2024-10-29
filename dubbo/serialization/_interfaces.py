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

import abc
from typing import Any, Union

__all__ = ["Serializer", "Deserializer", "SerializationError", "ensure_bytes"]


class SerializationError(Exception):
    """
    Serialization error.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


def ensure_bytes(obj: Union[bytes, bytearray, memoryview]) -> bytes:
    """
    Ensure that the input object is bytes or can be converted to bytes.
    :param obj: The object to ensure.
    :type obj: Union[bytes, bytearray, memoryview]
    :return: The bytes object.
    :rtype: bytes
    """

    if isinstance(obj, bytes):
        return obj
    elif isinstance(obj, (bytearray, memoryview)):
        return bytes(obj)
    else:
        raise SerializationError(
            f"SerializationError: The incoming object is of type '{type(obj).__name__}', "
            f"which is not supported. Expected types are 'bytes', 'bytearray', or 'memoryview'.\n"
            f"Current object type: '{type(obj).__name__}'.\n"
            f"Please provide data of the correct type or configure the serializer to handle the current input type."
        )


class Serializer(abc.ABC):
    """
    Interface for serializer.
    """

    @abc.abstractmethod
    def serialize(self, *args, **kwargs) -> bytes:
        """
        Serialize an object to bytes.
        :param args: The arguments to serialize.
        :param kwargs: The keyword arguments to serialize.
        :return: The serialized bytes.
        :rtype: bytes
        :raises SerializationError: If serialization fails.
        """
        raise NotImplementedError()


class Deserializer(abc.ABC):
    """
    Interface for deserializer.
    """

    @abc.abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize bytes to an object.
        :param data: The bytes to deserialize.
        :type data: bytes
        :return: The deserialized object.
        :rtype: Any
        :raises SerializationError: If deserialization fails.
        """
        raise NotImplementedError()
