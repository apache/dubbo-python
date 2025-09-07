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

from enum import Enum
from typing import Any

from dubbo.codec.json_codec import TypeHandler

__all__ = ["EnumHandler"]


class EnumHandler(TypeHandler):
    """
    Type handler for Enum objects.

    Serializes Enum instances with module path and value
    for proper reconstruction.
    """

    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Check if this handler can serialize Enum types.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if object is an Enum instance.
        :rtype: bool
        """
        return isinstance(obj, Enum)

    def serialize_to_dict(self, obj: Enum) -> dict[str, Any]:
        """
        Serialize Enum to dictionary representation.

        :param obj: The Enum to serialize.
        :type obj: Enum
        :return: Dictionary with enum class path and value.
        :rtype: dict[str, Any]
        """
        return {"$enum": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}", "$value": obj.value}
