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

from pathlib import Path
from typing import Any, Union
from uuid import UUID

from dubbo.codec.json_codec import TypeHandler

__all__ = ["SimpleTypesHandler"]


class SimpleTypesHandler(TypeHandler):
    """
    Type handler for simple types like UUID and Path.

    Handles serialization of UUID and Path objects to string representations.
    """

    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Check if this handler can serialize simple types.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if object is UUID or Path.
        :rtype: bool
        """
        return obj_type in (UUID, Path) or isinstance(obj, Path)

    def serialize_to_dict(self, obj: Union[UUID, Path]) -> dict[str, str]:
        """
        Serialize UUID or Path to dictionary representation.

        :param obj: The object to serialize.
        :type obj: Union[UUID, Path]
        :return: Dictionary representation with type marker.
        :rtype: Dict[str, str]
        """
        if isinstance(obj, UUID):
            return {"$uuid": str(obj)}
        elif isinstance(obj, Path):
            return {"$path": str(obj)}
        else:
            raise ValueError(f"Unsupported simple type: {type(obj)}")
