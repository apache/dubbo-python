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
from typing import Any, Optional

from dubbo.constants.type_constants import DeserializingFunction, SerializingFunction
from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


class Serialization:
    """
    Serialization class
    Args:
        serializing_function(SerializingFunction): The serialization function
        deserializing_function(DeserializingFunction): The deserialization function
    """

    def __init__(
        self,
        serializing_function: Optional[SerializingFunction] = None,
        deserializing_function: Optional[DeserializingFunction] = None,
    ):
        self.serializing_function = serializing_function
        self.deserializing_function = deserializing_function

    def serialize(self, *args, **kwargs) -> bytes:
        """
        Serialize the given data
        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        Returns:
            bytes: The serialized data
            Exception: If the serialization fails
        """
        # serialize the data
        if self.serializing_function:
            try:
                return self.serializing_function(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    "Serialization send error, please check the incoming serialization function"
                )
                raise e
        else:
            # check if the data is bytes -> args[0]
            if isinstance(args[0], bytes):
                return args[0]
            else:
                err_msg = "The args[0] is not bytes, you should pass parameters of type bytes, or set the serialization function"
                logger.error(err_msg)
                raise ValueError(err_msg)

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize the given data
        Args:
            data(bytes): The data to deserialize
        Returns:
            Any: The deserialized data
            Exception: If the deserialization fails
        """
        # deserialize the data
        if not self.deserializing_function:
            return data
        else:
            try:
                return self.deserializing_function(data)
            except Exception as e:
                logger.exception(
                    "Deserialization send error, please check the incoming deserialization function"
                )
                raise e
