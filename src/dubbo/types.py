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
import enum
from dataclasses import dataclass
from typing import Any, Callable

__all__ = [
    "SerializingFunction",
    "DeserializingFunction",
    "RpcType",
    "RpcTypes",
]

SerializingFunction = Callable[..., bytes]
DeserializingFunction = Callable[[bytes], Any]


@dataclass
class RpcType:
    """
    RpcType
    """

    name: str
    client_stream: bool
    server_stream: bool


@enum.unique
class RpcTypes(enum.Enum):
    UNARY = RpcType("Unary", False, False)
    CLIENT_STREAM = RpcType("ClientStream", True, False)
    SERVER_STREAM = RpcType("ServerStream", False, True)
    BI_STREAM = RpcType("BiStream", True, True)

    @classmethod
    def from_name(cls, name: str) -> RpcType:
        """
        Get RpcType by name. Case-insensitive.
        :param name: RpcType name
        :return: RpcType
        """
        for item in cls:
            # ignore case
            if item.value.name.lower() == name.lower():
                return item.value
        raise ValueError(f"Unknown RpcType name: {name}")
