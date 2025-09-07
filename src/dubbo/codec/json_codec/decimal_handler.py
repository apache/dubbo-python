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

from decimal import Decimal
from typing import Any

from dubbo.codec.json_codec import TypeHandler

__all__ = ["DecimalHandler"]


class DecimalHandler(TypeHandler):
    """
    Type handler for Decimal objects.

    Serializes Decimal objects to string representation
    for precision preservation.
    """

    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Check if this handler can serialize Decimal types.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if object is Decimal.
        :rtype: bool
        """
        return obj_type is Decimal

    def serialize_to_dict(self, obj: Decimal) -> dict[str, str]:
        """
        Serialize Decimal to dictionary representation.

        :param obj: The Decimal to serialize.
        :type obj: Decimal
        :return: dictionary representation with string value.
        :rtype: dict[str, str]
        """
        return {"$decimal": str(obj)}
