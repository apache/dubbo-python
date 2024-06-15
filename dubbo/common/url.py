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
from urllib import parse


class URL:
    """
    URL - Uniform Resource Locator

    url example:
    - http://www.facebook.com/friends?param1=value1&param2=value2
    - http://username:password@10.20.130.230:8080/list?version=1.0.0
    - ftp://username:password@192.168.1.7:21/1/read.txt
    - registry://192.168.1.7:9090/org.apache.dubbo.service1?param1=value1&param2=value2
    """

    def __init__(
        self,
        protocol: str,
        host: Optional[str],
        port: Optional[int],
        username: Optional[str] = None,
        password: Optional[str] = None,
        path: Optional[str] = None,
        parameters: Optional[Dict[str, str]] = None,
    ):
        """
        Initializes the URL with the given components.

        Args:
            protocol (str): The protocol of the URL.
            host (Optional[str]): The host of the URL.
            port (Optional[int]): The port number of the URL.
            username (Optional[str]): The username for URL authentication.
            password (Optional[str]): The password for URL authentication.
            path (Optional[str]): The path of the URL.
            parameters (Optional[Dict[str, str]]): The query parameters of the URL.
        """
        self._protocol = protocol
        self._host = host
        self._port = port
        # location -> host:port
        self._location = f"{host}:{port}" if host and port else host or None
        self._username = username
        self._password = password
        self._path = path
        self._parameters = parameters or {}

    @property
    def protocol(self) -> str:
        """
        Gets the protocol of the URL.

        Returns:
            str: The protocol of the URL.
        """
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: str) -> None:
        """
        Sets the protocol of the URL.

        Args:
            protocol (str): The protocol to set.
        """
        self._protocol = protocol

    @property
    def location(self) -> Optional[str]:
        """
        Gets the location (host:port) of the URL.

        Returns:
            Optional[str]: The location of the URL.
        """
        return self._location

    @property
    def host(self) -> Optional[str]:
        """
        Gets the host of the URL.

        Returns:
            Optional[str]: The host of the URL.
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
            Optional[int]: The port of the URL.
        """
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        """
        Sets the port of the URL.

        Args:
            port (int): The port to set.
        """
        self._port = max(port, 0)
        self._location = f"{self.host}:{port}" if port else self.host

    @property
    def username(self) -> Optional[str]:
        """
        Gets the username for URL authentication.

        Returns:
            Optional[str]: The username for URL authentication.
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
    def password(self) -> Optional[str]:
        """
        Gets the password for URL authentication.

        Returns:
            Optional[str]: The password for URL authentication.
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
    def path(self) -> Optional[str]:
        """
        Gets the path of the URL.

        Returns:
            Optional[str]: The path of the URL.
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

    @property
    def parameters(self) -> Dict[str, str]:
        """
        Gets the query parameters of the URL.

        Returns:
            Optional[Dict[str, str]]: The query parameters of the URL.
        """
        return self._parameters

    @parameters.setter
    def parameters(self, parameters: Dict[str, str]) -> None:
        """
        Sets the query parameters of the URL.

        Args:
            parameters (Dict[str, str]): The query parameters to set.
        """
        self._parameters = parameters

    def get_parameter(self, key: str) -> Optional[str]:
        """
        Gets a query parameter from the URL.

        Args:
            key (str): The parameter name.

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

    def build_string(self, encode: bool = False) -> str:
        """
        Generates the URL string based on the current components.

        Args:
            encode (bool): If True, the URL will be percent-encoded.

        Returns:
            str: The generated URL string.
        """
        # Set protocol
        url = f"{self.protocol}://" if self.protocol else ""
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
        if self.parameters:
            url += "?" + "&".join([f"{k}={v}" for k, v in self.parameters.items()])
        # If the URL needs to be encoded, encode it
        if encode:
            url = parse.quote(url)
        return url

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
            raise ValueError()

        # If the URL is encoded, decode it
        if encoded:
            url = parse.unquote(url)

        if "://" not in url:
            raise ValueError("Invalid URL format: missing protocol")

        parsed_url = parse.urlparse(url)

        protocol = parsed_url.scheme
        host = parsed_url.hostname
        port = parsed_url.port
        username = parsed_url.username
        password = parsed_url.password
        parameters = {k: v[0] for k, v in parse.parse_qs(parsed_url.query).items()}
        path = parsed_url.path.lstrip("/")

        if not protocol:
            raise ValueError("Invalid URL format: missing protocol.")
        return URL(protocol, host, port, username, password, path, parameters)