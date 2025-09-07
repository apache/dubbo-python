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
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

__all__ = [
    "ParameterDescriptor",
    "MethodDescriptor",
    "TransportCodec",
    "SerializationEncoder",
    "SerializationDecoder",
    "Codec",
]

logger = logging.getLogger(__name__)


@dataclass
class ParameterDescriptor:
    """Information about a method parameter"""

    name: str
    annotation: Any
    is_required: bool = True
    default_value: Any = None


@dataclass
class MethodDescriptor:
    """Method descriptor with function details"""

    function: Callable
    name: str
    parameters: list[ParameterDescriptor]
    return_parameter: ParameterDescriptor
    documentation: Optional[str] = None


class TransportCodec(abc.ABC):
    """
    The transport codec interface.
    """

    @classmethod
    @abc.abstractmethod
    def get_transport_type(cls) -> str:
        """
        Get transport type of current codec
        :return: The transport type.
        :rtype: str
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_encoder(self) -> "SerializationEncoder":
        """
        Get encoder instance
        :return: The encoder.
        :rtype: SerializationEncoder
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_decoder(self) -> "SerializationDecoder":
        """
        Get decoder instance
        :return: The decoder.
        :rtype: SerializationDecoder
        """
        raise NotImplementedError()


class SerializationEncoder(abc.ABC):
    """
    The serialization encoder interface.
    """

    @abc.abstractmethod
    def encode(self, arguments: tuple[Any, ...]) -> bytes:
        """
        Encode arguments to bytes.
        :param arguments: The arguments to encode.
        :type arguments: tuple[Any, ...]
        :return: The encoded bytes.
        :rtype: bytes
        """
        raise NotImplementedError()


class SerializationDecoder(abc.ABC):
    """
    The serialization decoder interface.
    """

    @abc.abstractmethod
    def decode(self, data: bytes) -> Any:
        """
        Decode bytes to object.
        :param data: The data to decode.
        :type data: bytes
        :return: The decoded object.
        :rtype: Any
        """
        raise NotImplementedError()


class Codec(abc.ABC):
    """
    Base codec interface for encoding and decoding data.
    """

    def __init__(self, model_type: Optional[type[Any]] = None, **kwargs):
        """
        Initialize a codec
        :param model_type: Optional model type for structured encoding/decoding
        :type model_type: Optional[type[Any]]
        :param kwargs: Additional codec configuration
        """
        self.model_type = model_type

    @abc.abstractmethod
    def encode(self, data: Any) -> bytes:
        """
        Encode data into bytes
        :param data: The data to encode.
        :type data: Any
        :return: Encoded byte representation
        :rtype: bytes
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def decode(self, data: bytes) -> Any:
        """
        Decode bytes into object
        :param data: The bytes to decode.
        :type data: bytes
        :return: Decoded object
        :rtype: Any
        """
        raise NotImplementedError()
