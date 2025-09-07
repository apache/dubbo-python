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
from typing import Any, Optional

__all__ = [
    "SerializationException",
    "DeserializationException",
    "ProtobufSerialization",
    "ProtobufEncoder",
    "ProtobufDecoder",
]


class SerializationException(Exception):
    """Exception raised when encoding or serialization fails."""

    def __init__(self, message: str, *, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class DeserializationException(Exception):
    """Exception raised when decoding or deserialization fails."""

    def __init__(self, message: str, *, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class ProtobufSerialization(abc.ABC):
    """
    The protobuf serialization interface.
    """

    @classmethod
    @abc.abstractmethod
    def get_serialization_type(cls) -> str:
        """
        Get serialization type of current implementation
        :return: The serialization type.
        :rtype: str
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def can_handle(self, obj: Any, obj_type: Optional[type] = None) -> bool:
        """
        Check if this serialization can handle the given object/type
        :param obj: The object to check
        :param obj_type: The type to check
        :return: True if can handle, False otherwise
        :rtype: bool
        """
        raise NotImplementedError()


class ProtobufEncoder(ProtobufSerialization, abc.ABC):
    """
    The protobuf encoding interface.
    """

    @abc.abstractmethod
    def encode(self, obj: Any, obj_type: Optional[type] = None) -> bytes:
        """
        Encode the object to bytes.
        :param obj: The object to encode.
        :param obj_type: The type hint for encoding.
        :return: The encoded bytes.
        :rtype: bytes
        """
        raise NotImplementedError()


class ProtobufDecoder(ProtobufSerialization, abc.ABC):
    """
    The protobuf decoding interface.
    """

    @abc.abstractmethod
    def decode(self, data: bytes, target_type: type) -> Any:
        """
        Decode the data to object.
        :param data: The data to decode.
        :param target_type: The target type for decoding.
        :return: The decoded object.
        :rtype: Any
        """
        raise NotImplementedError()
