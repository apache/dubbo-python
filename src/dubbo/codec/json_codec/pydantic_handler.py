#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Optional

from dubbo.codec.json_codec import TypeHandler

__all__ = ["PydanticHandler"]


class PydanticHandler(TypeHandler):
    """
    Type handler for Pydantic models.

    Handles serialization of Pydantic BaseModel instances with proper
    model reconstruction support.
    """

    def __init__(self):
        try:
            from pydantic import BaseModel, create_model

            self.BaseModel = BaseModel
            self.create_model = create_model
            self.available = True
        except ImportError:
            self.available = False

    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        """
        Check if this handler can serialize Pydantic models.

        :param obj: The object to check.
        :type obj: Any
        :param obj_type: The type of the object.
        :type obj_type: type
        :return: True if object is a Pydantic BaseModel and library is available.
        :rtype: bool
        """
        return self.available and isinstance(obj, self.BaseModel)

    def serialize_to_dict(self, obj: Any) -> dict[str, Any]:
        """
        Serialize Pydantic model to dictionary representation.

        :param obj: The Pydantic model to serialize.
        :type obj: BaseModel
        :return: Dictionary representation with model metadata.
        :rtype: dict[str, Any]
        """
        if not self.available:
            raise ImportError("Pydantic not available")

        # Use model_dump if available (Pydantic v2), otherwise use dict (Pydantic v1)
        if hasattr(obj, "model_dump"):
            model_data = obj.model_dump()
        else:
            model_data = obj.dict()

        return {
            "__pydantic_model__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
            "__model_data__": model_data,
        }

    def create_parameter_model(self, parameter_types: Optional[list[type]] = None):
        """
        Create a Pydantic model for parameter wrapping.

        :param parameter_types: List of parameter types to wrap.
        :type parameter_types: Optional[list[type]]
        :return: Dynamically created Pydantic model or None.
        """
        if not self.available or parameter_types is None:
            return None

        model_fields = {f"param_{i}": (param_type, ...) for i, param_type in enumerate(parameter_types)}
        return self.create_model("ParametersModel", **model_fields)
