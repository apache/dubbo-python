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

from typing import Any, Dict, Optional

from ._interfaces import Invocation


class RpcInvocation(Invocation):
    """
    The RpcInvocation class is an implementation of the Invocation interface.
    Args:
        service_name (str): The name of the service.
        method_name (str): The name of the method.
        argument (Any): The method argument.
        attachments (Optional[Dict[str, str]]): Passed to the remote server during RPC call
        attributes (Optional[Dict[str, Any]]): Only used on the caller side, will not appear on the wire.
    """

    __slots__ = [
        "_service_name",
        "_method_name",
        "_argument",
        "_attachments",
        "_attributes",
    ]

    def __init__(
        self,
        service_name: str,
        method_name: str,
        argument: Any,
        attachments: Optional[Dict[str, str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self._service_name = service_name
        self._method_name = method_name
        self._argument = argument
        self._attachments = attachments or {}
        self._attributes = attributes or {}

    def add_attachment(self, key: str, value: str) -> None:
        self._attachments[key] = value

    def get_attachment(self, key: str) -> Optional[str]:
        return self._attachments.get(key, None)

    def add_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def get_attribute(self, key: str) -> Optional[Any]:
        return self._attributes.get(key, None)

    def get_service_name(self) -> str:
        return self._service_name

    def get_method_name(self) -> str:
        return self._method_name

    def get_argument(self) -> Any:
        return self._argument
