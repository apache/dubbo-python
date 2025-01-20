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

from typing import Optional, Union

from dubbo.protocol.triple.constants import GRpcCode
from dubbo.protocol.triple.exceptions import StatusRpcError
from dubbo.remoting.aio.http2.registries import HttpStatus


class TriRpcStatus:
    """
    RPC status.
    """

    __slots__ = ["_code", "_cause", "_description"]

    def __init__(
        self,
        code: GRpcCode,
        cause: Optional[Exception] = None,
        description: Optional[str] = None,
    ):
        """
        Initialize the RPC status.
        :param code: The RPC status code.
        :type code: TriRpcCode
        :param description: The description.
        :type description: Optional[str]
        :param cause: The exception cause.
        :type cause: Optional[Exception]
        """
        if isinstance(code, int):
            code = GRpcCode.from_code(code)
        self._code = code
        self._description = description
        self._cause = cause

    @property
    def code(self) -> GRpcCode:
        return self._code

    @property
    def description(self) -> Optional[str]:
        return self._description

    @property
    def cause(self) -> Optional[Exception]:
        return self._cause

    def with_description(self, description: str) -> "TriRpcStatus":
        """
        Set the description.
        :param description: The description.
        :type description: str
        :return: The RPC status.
        :rtype: TriRpcStatus
        """
        self._description = description
        return self

    def with_cause(self, cause: Exception) -> "TriRpcStatus":
        """
        Set the cause.
        :param cause: The cause.
        :type cause: Exception
        :return: The RPC status.
        :rtype: TriRpcStatus
        """
        self._cause = cause
        return self

    def append_description(self, description: str) -> None:
        """
        Append the description.
        :param description: The description to append.
        :type description: str
        """
        if self._description:
            self._description += f"\n{description}"
        else:
            self._description = description

    def as_exception(self) -> Exception:
        """
        Convert the RPC status to an exception.
        :return: The exception.
        :rtype: Exception
        """
        return StatusRpcError(self)

    @staticmethod
    def limit_desc(description: str, limit: int = 1024) -> str:
        """
        Limit the description length.
        :param description: The description.
        :type description: str
        :param limit: The limit.(default: 1024)
        :type limit: int
        :return: The limited description.
        :rtype: str
        """
        if description and len(description) > limit:
            return f"{description[:limit]}..."
        return description

    @classmethod
    def from_rpc_code(cls, code: Union[int, GRpcCode]):
        if isinstance(code, int):
            code = GRpcCode.from_code(code)
        return cls(code)

    @classmethod
    def from_http_code(cls, code: Union[int, HttpStatus]):
        http_status = HttpStatus.from_code(code) if isinstance(code, int) else code
        rpc_code = GRpcCode.UNKNOWN
        if HttpStatus.is_1xx(http_status) or http_status in [
            HttpStatus.BAD_REQUEST,
            HttpStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
        ]:
            rpc_code = GRpcCode.INTERNAL
        elif http_status == HttpStatus.UNAUTHORIZED:
            rpc_code = GRpcCode.UNAUTHENTICATED
        elif http_status == HttpStatus.FORBIDDEN:
            rpc_code = GRpcCode.PERMISSION_DENIED
        elif http_status == HttpStatus.NOT_FOUND:
            rpc_code = GRpcCode.NOT_FOUND
        elif http_status in [
            HttpStatus.BAD_GATEWAY,
            HttpStatus.TOO_MANY_REQUESTS,
            HttpStatus.SERVICE_UNAVAILABLE,
            HttpStatus.GATEWAY_TIMEOUT,
        ]:
            rpc_code = GRpcCode.UNAVAILABLE

        return cls(rpc_code)

    def __repr__(self):
        return f"TriRpcStatus(code={self._code}, cause={self._cause}, description={self._description})"
