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

from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from dubbo.codec.json_codec import JsonCodec

__all__ = ["UJsonCodec"]


class UJsonCodec(JsonCodec):
    """
    ujson codec implementation for high-performance JSON encoding/decoding.

    Uses the ujson library if available, otherwise falls back gracefully.
    """

    def __init__(self):
        try:
            import ujson

            self.ujson = ujson
            self.available = True
        except ImportError:
            self.available = False

    def encode(self, obj: Any) -> bytes:
        """
        Encode an object to JSON bytes using ujson.

        :param obj: The object to encode.
        :type obj: Any
        :return: The encoded JSON bytes.
        :rtype: bytes
        """
        if not self.available:
            raise ImportError("ujson not available")
        return self.ujson.dumps(obj, ensure_ascii=False, default=self._default_handler).encode("utf-8")

    def decode(self, data: bytes) -> Any:
        """
        Decode JSON bytes to an object using ujson.

        :param data: The JSON bytes to decode.
        :type data: bytes
        :return: The decoded object.
        :rtype: Any
        """
        if not self.available:
            raise ImportError("ujson not available")
        return self.ujson.loads(data.decode("utf-8"))

    def can_handle(self, obj: Any) -> bool:
        """
        Check if this codec can handle the given object.

        :param obj: The object to check.
        :type obj: Any
        :return: True if ujson is available.
        :rtype: bool
        """
        return self.available

    def _default_handler(self, obj):
        """
        Handle types not supported natively by ujson.

        :param obj: The object to serialize.
        :return: Serialized representation.
        """
        if isinstance(obj, datetime):
            iso_string = obj.isoformat()
            if obj.tzinfo is None:
                iso_string += "Z"
            elif str(obj.tzinfo) == "UTC" or obj.utcoffset().total_seconds() == 0:
                iso_string = iso_string.replace("+00:00", "Z")
            return {"$date": iso_string}
        elif isinstance(obj, date):
            return {"$dateOnly": obj.isoformat()}
        elif isinstance(obj, time):
            return {"$timeOnly": obj.isoformat()}
        elif isinstance(obj, Decimal):
            return {"$decimal": str(obj)}
        elif isinstance(obj, set):
            return {"$set": list(obj)}
        elif isinstance(obj, frozenset):
            return {"$frozenset": list(obj)}
        elif isinstance(obj, UUID):
            return {"$uuid": str(obj)}
        elif isinstance(obj, Path):
            return {"$path": str(obj)}
        return {"$fallback": str(obj), "$type": type(obj).__name__}
