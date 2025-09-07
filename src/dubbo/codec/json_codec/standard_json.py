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
from typing import Any

from dubbo.codec.json_codec import JsonCodec

__all__ = ["StandardJsonCodec"]


class StandardJsonCodec(JsonCodec):
    """
    Standard library JSON codec implementation.

    Uses Python's built-in json module for encoding and decoding.
    This is the fallback codec that can handle any object.
    """

    def encode(self, obj: Any) -> bytes:
        """
        Encode an object to JSON bytes using standard library.

        :param obj: The object to encode.
        :type obj: Any
        :return: The encoded JSON bytes.
        :rtype: bytes
        """
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def decode(self, data: bytes) -> Any:
        """
        Decode JSON bytes to an object using standard library.

        :param data: The JSON bytes to decode.
        :type data: bytes
        :return: The decoded object.
        :rtype: Any
        """
        return json.loads(data.decode("utf-8"))

    def can_handle(self, obj: Any) -> bool:
        """
        Check if this codec can handle the given object.
        Standard JSON can handle any object as fallback.

        :param obj: The object to check.
        :type obj: Any
        :return: Always True (fallback codec).
        :rtype: bool
        """
        return True
