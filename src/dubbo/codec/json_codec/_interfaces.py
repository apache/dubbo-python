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
from typing import Any

__all__ = ["JsonCodec", "TypeHandler"]


class JsonCodec(abc.ABC):
    """
    The JSON codec interface for encoding and decoding objects to/from JSON bytes.
    """

    @abc.abstractmethod
    def encode(self, obj: Any) -> bytes:
        """
        Encode an object to JSON bytes.

        :param obj: The object to encode.
        :type obj: Any
        :return: The encoded JSON bytes.
        :rtype: bytes
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def decode(self, data: bytes) -> Any:
        """
        Decode JSON bytes to an object.

        :param data: The JSON bytes to decode.
        :type data: bytes
        :return: The decoded object.
        :rtype: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def can_handle(self, obj: Any) -> bool:
        """
        Check if this codec can handle the given object.

        :param obj: The object to check.
        :type obj: Any
        :return: True if this codec can handle the object.
        :rtype: bool
        """
        raise NotImplementedError()


class TypeHandler(abc.ABC):
    """
    Base interface for all type-specific serializers.

    Each type handler should implement:
    - can_serialize_type: determine if the object can be serialized
    - serialize_to_dict: return a dict representation of the object
    """

    @abc.abstractmethod
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Returns True if this handler can serialize the given object/type.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if this handler can serialize the object.
        :rtype: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def serialize_to_dict(self, obj: Any) -> dict[str, Any]:
        """
        Serialize the object into a dictionary representation.

        :param obj: The object to serialize.
        :type obj: Any
        :return: The dictionary representation of the object.
        :rtype: dict[str, Any]
        """
        raise NotImplementedError()
