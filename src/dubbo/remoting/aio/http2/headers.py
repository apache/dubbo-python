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
from typing import Optional, Union


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

    @classmethod
    def to_list(cls) -> list[str]:
        """
        Get all pseudo-header names.
        Returns:
            The pseudo-header names list.
        """
        return [header.value for header in cls]


class HttpMethod(enum.Enum):
    """
    HTTP method types.
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

    __slots__ = ["_headers"]

    def __init__(self):
        self._headers: OrderedDict[str, Optional[str]] = OrderedDict()
        self._init()

    def _init(self):
        # keep the order of headers
        self._headers = {name: "" for name in PseudoHeaderName.to_list()}

    def add(self, name: str, value: str) -> None:
        self._headers[name] = str(value)

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return self._headers.get(name, default)

    @property
    def method(self) -> Optional[str]:
        return self.get(PseudoHeaderName.METHOD.value)

    @method.setter
    def method(self, value: Union[HttpMethod, str]) -> None:
        if isinstance(value, HttpMethod):
            value = value.value
        else:
            value = value.upper()
        self.add(PseudoHeaderName.METHOD.value, value)

    @property
    def scheme(self) -> Optional[str]:
        return self.get(PseudoHeaderName.SCHEME.value)

    @scheme.setter
    def scheme(self, value: str) -> None:
        self.add(PseudoHeaderName.SCHEME.value, value)

    @property
    def authority(self) -> Optional[str]:
        return self.get(PseudoHeaderName.AUTHORITY.value)

    @authority.setter
    def authority(self, value: str) -> None:
        self.add(PseudoHeaderName.AUTHORITY.value, value)

    @property
    def path(self) -> Optional[str]:
        return self.get(PseudoHeaderName.PATH.value)

    @path.setter
    def path(self, value: str) -> None:
        self.add(PseudoHeaderName.PATH.value, value)

    @property
    def status(self) -> Optional[str]:
        return self.get(PseudoHeaderName.STATUS.value)

    @status.setter
    def status(self, value: str) -> None:
        self.add(PseudoHeaderName.STATUS.value, value)

    def to_list(self) -> list[tuple[str, str]]:
        """
        Convert the headers to a list. The list contains all non-None headers.
        :return: The headers list.
        :rtype: List[Tuple[str, str]]
        """
        headers = []
        pseudo_headers = PseudoHeaderName.to_list()
        for name, value in list(self._headers.items()):
            if name in pseudo_headers and value == "":
                continue
            headers.append((str(name), str(value) or ""))
        return headers

    def to_dict(self) -> OrderedDict[str, str]:
        """
        Convert the headers to an ordered dict.
        :return: The headers' dict.
        :rtype: OrderedDict[str, Optional[str]]
        """
        headers_dict = OrderedDict()
        for key, value in self._headers.items():
            if value is not None and value != "":
                headers_dict[key] = value
        return headers_dict

    def __repr__(self) -> str:
        return f"<Http2Headers {self.to_list()}>"

    @classmethod
    def from_list(cls, headers: list[tuple[str, str]]) -> "Http2Headers":
        """
        Create an Http2Headers object from a list.
        :param headers: The headers list.
        :type headers: List[Tuple[str, str]]
        :return: The Http2Headers object.
        :rtype: Http2Headers
        """
        http2_headers = cls()
        http2_headers._headers = dict(headers)  # type: ignore
        return http2_headers
