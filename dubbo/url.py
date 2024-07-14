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


class URL:
    """
    URL - Uniform Resource Locator.
    Args:
        scheme (str): The protocol of the URL.
        host (str): The host of the URL.
        port (int): The port number of the URL.
        username (str): The username for URL authentication.
        password (str): The password for URL authentication.
        path (str): The path of the URL.
        parameters (Dict[str, str]): The query parameters of the URL.
        attributes (Dict[str, Any]): The attributes of the URL. (non-transferable)

    url example:
    - http://www.facebook.com/friends?param1=value1&param2=value2
    - http://username:password@10.20.130.230:8080/list?version=1.0.0
    - ftp://username:password@192.168.1.7:21/1/read.txt
    - registry://192.168.1.7:9090/org.apache.dubbo.service1?param1=value1&param2=value2
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
        self._scheme = scheme
        self._host = host
        self._port = port
        # location -> host:port
        self._location = f"{host}:{port}" if port else host
        self._username = username
        self._password = password
        self._path = path
        self._parameters = parameters or {}
        self._attributes = attributes or {}

    @property
    def scheme(self) -> str:
        """
        Gets the protocol of the URL.

        Returns:
            str: The protocol of the URL.
        """
        return self._scheme

    @scheme.setter
    def scheme(self, scheme: str) -> None:
        """
        Sets the protocol of the URL.

        Args:
            scheme (str): The protocol to set.
        """
        self._scheme = scheme

    @property
    def location(self) -> str:
        """
        Gets the location (host:port) of the URL.

        Returns:
            str: The location of the URL.
        """
        return self._location

    @property
    def host(self) -> str:
        """
        Gets the host of the URL.

        Returns:
            str: The host of the URL.
        """
        return self._host

    @host.setter
    def host(self, host: str) -> None:
        """
        Sets the host of the URL.

        Args:
            host (str): The host to set.
        """
        self._host = host
        self._location = f"{host}:{self.port}" if self.port else host

    @property
    def port(self) -> Optional[int]:
        """
        Gets the port of the URL.

        Returns:
            int: The port of the URL.
        """
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        """
        Sets the port of the URL.

        Args:
            port (int): The port to set.
        """
        port = port if port > 0 else None
        self._location = f"{self.host}:{port}" if port else self.host

    @property
    def username(self) -> str:
        """
        Gets the username for URL authentication.

        Returns:
            str: The username for URL authentication.
        """
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        """
        Sets the username for URL authentication.

        Args:
            username (str): The username to set.
        """
        self._username = username

    @property
    def password(self) -> str:
        """
        Gets the password for URL authentication.

        Returns:
            [str]: The password for URL authentication.
        """
        return self._password

    @password.setter
    def password(self, password: str) -> None:
        """
        Sets the password for URL authentication.

        Args:
            password (str): The password to set.
        """
        self._password = password

    @property
    def path(self) -> str:
        """
        Gets the path of the URL.

        Returns:
            str: The path of the URL.
        """
        return self._path

    @path.setter
    def path(self, path: str) -> None:
        """
        Sets the path of the URL.

        Args:
            path (str): The path to set.
        """
        self._path = path

    def get_parameter(self, key: str) -> Optional[str]:
        """
        Gets a query parameter from the URL.

        Args:
            key (Optional[str]): The parameter name.

        Returns:
            str or None: The parameter value. If the parameter does not exist, returns None.
        """
        return self._parameters.get(key, None)

    def add_parameter(self, key: str, value: Any) -> None:
        """
        Adds a query parameter to the URL.

        Args:
            key (str): The parameter name.
            value (Any): The parameter value.
        """
        self._parameters[key] = str(value) if value is not None else ""

    @property
    def attributes(self):
        """
        Gets the attributes of the URL.
        Returns:
            Dict[str, Any]: The attributes of the URL.
        """
        return self._attributes

    def build_string(self, encode: bool = False) -> str:
        """
        Generates the URL string based on the current components.

        Args:
            encode (bool): If True, the URL will be percent-encoded.

        Returns:
            str: The generated URL string.
        """
        # Set protocol
        url = f"{self.scheme}://" if self.scheme else ""
        # Set auth
        if self.username:
            url += f"{self.username}"
            if self.password:
                url += f":{self.password}"
            url += "@"
        # Set location
        url += self.location if self.location else ""
        # Set path
        url += "/"
        if self.path:
            url += f"{self.path}"
        # Set params
        if self._parameters:
            url += "?" + "&".join([f"{k}={v}" for k, v in self._parameters.items()])
        # If the URL needs to be encoded, encode it
        if encode:
            url = parse.quote(url)
        return url

    def clone_without_attributes(self) -> "URL":
        """
        Clones the URL object without the attributes.
        Returns:
            URL: The cloned URL object.
        """
        return URL(
            self.scheme,
            self.host,
            self.port,
            self.username,
            self.password,
            self.path,
            self._parameters.copy(),
        )

    def clone(self) -> "URL":
        """
        Clones the URL object. Ignores the attributes.

        Returns:
            URL: The cloned URL object.
        """
        return URL(
            self.scheme,
            self.host,
            self.port,
            self.username,
            self.password,
            self.path,
            self._parameters.copy(),
            copy.deepcopy(self._attributes),
        )

    def __str__(self) -> str:
        """
        Returns the URL string when the object is converted to a string.

        Returns:
            str: The generated URL string.
        """
        return self.build_string()

    @classmethod
    def value_of(cls, url: str, encoded: bool = False) -> "URL":
        """
        Creates a URL object from a URL string.

        Args:
            url (str): The URL string to parse. format: [protocol://][username:password@][host:port]/[path]
            encoded (bool): If True, the URL string is percent-encoded and will be decoded.

        Returns:
            URL: The created URL object.
        """
        if not url:
            raise ValueError("URL string cannot be empty or None.")

        # If the URL is encoded, decode it
        if encoded:
            url = parse.unquote(url)

        if "://" not in url:
            raise ValueError("Invalid URL format: missing protocol")

        parsed_url = parse.urlparse(url)

        protocol = parsed_url.scheme
        host = parsed_url.hostname or ""
        port = parsed_url.port or None
        username = parsed_url.username or ""
        password = parsed_url.password or ""
        parameters = {k: v[0] for k, v in parse.parse_qs(parsed_url.query).items()}
        path = parsed_url.path.lstrip("/")

        if not protocol:
            raise ValueError("Invalid URL format: missing protocol.")
        return URL(protocol, host, port, username, password, path, parameters)
