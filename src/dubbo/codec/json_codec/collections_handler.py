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

from typing import Any, Union

from dubbo.codec.json_codec import TypeHandler

__all__ = ["CollectionHandler"]


class CollectionHandler(TypeHandler):
    """
    Type handler for set and frozenset collections.

    Serializes sets and frozensets to list format with type markers
    for proper reconstruction.
    """

    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Check if this handler can serialize collection types.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if object is set or frozenset.
        :rtype: bool
        """
        return obj_type in (set, frozenset)

    def serialize_to_dict(self, obj: Union[set, frozenset]) -> dict[str, list]:
        """
        Serialize set/frozenset to dictionary representation.

        :param obj: The collection to serialize.
        :type obj: Union[set, frozenset]
        :return: dictionary representation with type marker.
        :rtype: dict[str, list]
        """
        if isinstance(obj, frozenset):
            return {"$frozenset": list(obj)}
        else:
            return {"$set": list(obj)}
