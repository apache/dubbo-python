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
from collections import OrderedDict
from typing import List, Optional, Tuple, Union


class PseudoHeaderName(enum.Enum):
    """
    Pseudo-header names defined in RFC 7540 Section.
    See: https://datatracker.ietf.org/doc/html/rfc7540#section-8.1.2
    """

    SCHEME = ":scheme"
    # Request pseudo-headers
    METHOD = ":method"
    AUTHORITY = ":authority"
    PATH = ":path"
    # Response pseudo-headers
    STATUS = ":status"


class MethodType(enum.Enum):
    """
    HTTP/2 method types.
    """

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"
    TRACE = "TRACE"
    CONNECT = "CONNECT"


class Http2Headers:
    """
    HTTP/2 headers.
    """

    def __init__(self):
        self._headers: OrderedDict[str, Optional[str]] = OrderedDict()
        self._init()

    def _init(self):
        # keep the order of headers
        self._headers[PseudoHeaderName.SCHEME.value] = None
        self._headers[PseudoHeaderName.METHOD.value] = None
        self._headers[PseudoHeaderName.AUTHORITY.value] = None
        self._headers[PseudoHeaderName.PATH.value] = None
        self._headers[PseudoHeaderName.STATUS.value] = None

    def add(self, name: str, value: str) -> None:
        """
        Add a header.
        Args:
            name: The header name.
            value: The header value.
        """
        self._headers[name] = value

    def get(self, name: str) -> Optional[str]:
        """
        Get the header value.
        Returns:
            The header value: If the header exists, return the value. Otherwise, return None.
        """
        return self._headers.get(name, None)

    @property
    def method(self) -> Optional[str]:
        """
        Get the method.
        """
        return self.get(PseudoHeaderName.METHOD.value)

    @method.setter
    def method(self, value: Union[MethodType, str]) -> None:
        """
        Set the method.
        Args:
            value: The method value.
        """
        if isinstance(value, MethodType):
            value = value.value
        else:
            value = value.upper()
        self.add(PseudoHeaderName.METHOD.value, value)

    @property
    def scheme(self) -> Optional[str]:
        """
        Get the scheme.
        """
        return self.get(PseudoHeaderName.SCHEME.value)

    @scheme.setter
    def scheme(self, value: str) -> None:
        """
        Set the scheme.
        Args:
            value: The scheme value.
        """
        self.add(PseudoHeaderName.SCHEME.value, value)

    @property
    def authority(self) -> Optional[str]:
        """
        Get the authority.
        """
        return self.get(PseudoHeaderName.AUTHORITY.value)

    @authority.setter
    def authority(self, value: str) -> None:
        """
        Set the authority.
        Args:
            value: The authority value.
        """
        self.add(PseudoHeaderName.AUTHORITY.value, value)

    @property
    def path(self) -> Optional[str]:
        """
        Get the path.
        """
        return self.get(PseudoHeaderName.PATH.value)

    @path.setter
    def path(self, value: str) -> None:
        """
        Set the path.
        Args:
            value: The path value.
        """
        self.add(PseudoHeaderName.PATH.value, value)

    @property
    def status(self) -> Optional[str]:
        """
        Get the status code.
        """
        return self.get(PseudoHeaderName.STATUS.value)

    @status.setter
    def status(self, value: str) -> None:
        """
        Set the status code.
        Args:
            value: The status code.
        """
        self.add(PseudoHeaderName.STATUS.value, value)

    def to_list(self) -> List[Tuple[str, str]]:
        """
        Convert the headers to a list. The list contains all non-None headers.
        Returns:
            The headers list.
        """
        return [
            (name, value) for name, value in self._headers.items() if value is not None
        ]

    def __repr__(self) -> str:
        return f"<Http2Headers {self.to_list()}>"

    @classmethod
    def from_list(cls, headers: List[Tuple[str, str]]) -> "Http2Headers":
        """
        Create an Http2Headers object from a list.
        Args:
            headers: The headers list.
        Returns:
            The Http2Headers object.
        """
        http2_headers = cls()
        for name, value in headers:
            http2_headers.add(name, value)
        return http2_headers
