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
from typing import Any, Callable, Optional


class MethodConfig:
    """
    MethodConfig is a configuration class for a method.
    Attributes:
        _interface_name (str): The name of the interface.
        _name (str): The name of the method.
        _request_serialize (Optional[Callable[..., Any]]): The request serialization function.
        _response_deserialize (Optional[Callable[..., Any]]): The response deserialization function.
    """

    _interface_name: str
    _name: str
    _request_serialize: Optional[Callable[..., Any]]
    _response_deserialize: Optional[Callable[..., Any]]

    __slots__ = [
        "_interface_name",
        "_name",
        "_request_serialize",
        "_response_deserialize",
    ]

    def __init__(
        self,
        interface_name: str,
        name: str,
        request_serialize: Optional[Callable[..., Any]] = None,
        response_deserialize: Optional[Callable[..., Any]] = None,
    ):
        self._interface_name = interface_name
        self._name = name
        self._request_serialize = request_serialize
        self._response_deserialize = response_deserialize

    @property
    def interface_name(self) -> str:
        return self._interface_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def request_serialize(self) -> Optional[Callable[..., Any]]:
        return self._request_serialize

    @property
    def response_deserialize(self) -> Optional[Callable[..., Any]]:
        return self._response_deserialize
