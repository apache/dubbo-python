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

import copy
from typing import Any, Dict, Optional
from urllib import parse
from urllib.parse import urlencode, urlunparse

from dubbo.constants import common_constants

__all__ = ["URL", "create_url"]


def create_url(url: str, encoded: bool = False) -> "URL":
    """
    Creates a URL object from a URL string.

    This function takes a URL string and converts it into a URL object.
    If the 'encoded' parameter is set to True, the URL string will be decoded before being converted.

    :param url: The URL string to be converted into a URL object.
    :type url: str
    :param encoded: Determines if the URL string should be decoded before being converted. Defaults to False.
    :type encoded: bool
    :return: A URL object.
    :rtype: URL
    :raises ValueError: If the URL format is invalid.
    """
    # If the URL is encoded, decode it
    if encoded:
        url = parse.unquote(url)

    if common_constants.PROTOCOL_SEPARATOR not in url:
        raise ValueError("Invalid URL format: missing protocol")

    parsed_url = parse.urlparse(url)

    if not parsed_url.scheme:
        raise ValueError("Invalid URL format: missing scheme.")

    return URL(
        parsed_url.scheme,
        parsed_url.hostname or "",
        parsed_url.port,
        parsed_url.username or "",
        parsed_url.password or "",
        parsed_url.path.lstrip("/"),
        {k: v[0] for k, v in parse.parse_qs(parsed_url.query).items()},
    )


class URL:
    """
    URL - Uniform Resource Locator.
    """

    __slots__ = [
        "_scheme",
        "_host",
        "_port",
        "_location",
        "_username",
        "_password",
        "_path",
        "_parameters",
        "_attributes",
    ]

    def __init__(
        self,
        scheme: str,
        host: str,
        port: Optional[int] = None,
        username: str = "",
        password: str = "",
        path: str = "",
        parameters: Optional[Dict[str, str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the URL object.

        :param scheme: The scheme of the URL (e.g., 'http', 'https').
        :type scheme: str
        :param host: The host of the URL.
        :type host: str
        :param port: The port number of the URL, defaults to None.
        :type port: int, optional
        :param username: The username for authentication, defaults to an empty string.
        :type username: str, optional
        :param password: The password for authentication, defaults to an empty string.
        :type password: str, optional
        :param path: The path of the URL, defaults to an empty string.
        :type path: str, optional
        :param parameters: The query parameters of the URL as a dictionary, defaults to None.
        :type parameters: Dict[str, str], optional
        :param attributes: Additional attributes of the URL as a dictionary, defaults to None.
        :type attributes: Dict[str, Any], optional
        """
        self._scheme = scheme
        self._host = host
        self._port = port
        self._location = f"{host}:{port}" if port else host
        self._username = username
        self._password = password
        self._path = path
        self._parameters = parameters or {}
        self._attributes = attributes or {}

    @property
    def scheme(self) -> str:
        """
        Get or set the scheme of the URL.

        :return: The scheme of the URL.
        :rtype: str
        """
        return self._scheme

    @scheme.setter
    def scheme(self, value: str):
        self._scheme = value

    @property
    def host(self) -> str:
        """
        Get or set the host of the URL.

        :return: The host of the URL.
        :rtype: str
        """
        return self._host

    @host.setter
    def host(self, value: str):
        self._host = value
        self._location = f"{self.host}:{self.port}" if self.port else self.host

    @property
    def port(self) -> Optional[int]:
        """
        Get or set the port of the URL.

        :return: The port of the URL.
        :rtype: int, optional
        """
        return self._port

    @port.setter
    def port(self, value: int):
        if value > 0:
            self._port = value
            self._location = f"{self.host}:{self.port}"

    @property
    def location(self) -> str:
        """
        Get or set the location (host:port) of the URL.

        :return: The location of the URL.
        :rtype: str
        """
        return self._location

    @location.setter
    def location(self, value: str):
        try:
            values = value.split(":")
            self.host = values[0]
            if len(values) == 2:
                self.port = int(values[1])
        except Exception as e:
            raise ValueError(f"Invalid location: {value}") from e

    @property
    def username(self) -> str:
        """
        Get or set the username for authentication.

        :return: The username.
        :rtype: str
        """
        return self._username

    @username.setter
    def username(self, value: str):
        self._username = value

    @property
    def password(self) -> str:
        """
        Get or set the password for authentication.

        :return: The password.
        :rtype: str
        """
        return self._password

    @password.setter
    def password(self, value: str):
        self._password = value

    @property
    def path(self) -> str:
        """
        Get or set the path of the URL.

        :return: The path of the URL.
        :rtype: str
        """
        return self._path

    @path.setter
    def path(self, value: str):
        self._path = value.lstrip("/")

    @property
    def parameters(self) -> Dict[str, str]:
        """
        Get the query parameters of the URL.

        :return: The query parameters as a dictionary.
        :rtype: Dict[str, str]
        """
        return self._parameters

    @property
    def attributes(self) -> Dict[str, Any]:
        """
        Get the additional attributes of the URL.

        :return: The attributes as a dictionary.
        :rtype: Dict[str, Any]
        """
        return self._attributes

    def to_str(
        self,
        contain_ip: bool = True,
        contain_user: bool = True,
        contain_path: bool = True,
        contain_parameters: bool = True,
        encode: bool = False,
    ) -> str:
        """
        Converts the URL to a string.
        :param contain_ip: Determines if the URL should contain the IP address. Defaults to True.
        :type contain_ip: bool
        :param contain_user: Determines if the URL should contain the username. Defaults to True.
        :type contain_user: bool
        :param contain_path: Determines if the URL should contain the path. Defaults to True.
        :type contain_path: bool
        :param contain_parameters: Determines if the URL should contain the parameters. Defaults to True.
        :param encode: Determines if the URL should be encoded. Defaults to False.
        :type encode: bool
        :return: The URL string.
        :rtype: str
        """

        # Construct the scheme part
        scheme = ""
        netloc = ""
        if contain_ip:
            scheme = self.scheme

            # Construct the netloc part
            if contain_user and self.username and self.password:
                netloc = f"{self.username}:{self.password}@{self.location}"
            else:
                netloc = self.location

        # Construct the path part
        path = self.path if contain_path else ""

        # Construct the query part
        query = urlencode(self.parameters) if contain_parameters else ""

        # Construct the URL
        url = ""
        if scheme or netloc or path or query:
            url = urlunparse((scheme, netloc, path, "", query, ""))

            if encode:
                url = parse.quote(url, safe="")

        return url

    def copy(self) -> "URL":
        """
        Copy the URL object.

        :return: A shallow copy of the URL object.
        :rtype: URL
        """
        return copy.copy(self)

    def deepcopy(self) -> "URL":
        """
        Deep copy the URL object.

        :return: A deep copy of the URL object.
        :rtype: URL
        """
        return copy.deepcopy(self)

    def __copy__(self) -> "URL":
        return URL(
            self.scheme,
            self.host,
            self.port,
            self.username,
            self.password,
            self.path,
            self.parameters.copy(),
            self.attributes.copy(),
        )

    def __deepcopy__(self, memo) -> "URL":
        return URL(
            self.scheme,
            self.host,
            self.port,
            self.username,
            self.password,
            self.path,
            copy.deepcopy(self.parameters, memo),
            copy.deepcopy(self.attributes, memo),
        )

    def __str__(self) -> str:
        return self.to_str()

    def __repr__(self) -> str:
        return self.to_str()
