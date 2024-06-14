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
from typing import Dict, Optional
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
        protocol: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
    ):
        """
        Initializes the URL with the given components.

        Args:
            protocol (Optional[str]): The protocol of the URL.
            host (Optional[str]): The host of the URL.
            port (Optional[int]): The port number of the URL.
            username (Optional[str]): The username for URL authentication.
            password (Optional[str]): The password for URL authentication.
            path (Optional[str]): The path of the URL.
            params (Optional[Dict[str, str]]): The query parameters of the URL.
        """
        self._protocol = protocol
        self._host = host
        self._port = port
        # address = host:port
        self._address = None if not host else f"{host}:{port}" if port else host
        self._username = username
        self._password = password
        self._path = path
        self._params = params

    @property
    def protocol(self) -> Optional[str]:
        """
        Gets the protocol of the URL.

        Returns:
            Optional[str]: The protocol of the URL.
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
    def address(self) -> Optional[str]:
        """
        Gets the address (host:port) of the URL.

        Returns:
            Optional[str]: The address of the URL.
        """
        return self._address

    @address.setter
    def address(self, address: str) -> None:
        """
        Sets the address (host:port) of the URL.

        Args:
            address (str): The address to set.
        """
        self._address = address
        if ":" in address:
            self._host, port = address.split(":")
            self._port = int(port)
        else:
            self._host = address
            self._port = None

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
        self._address = f"{host}:{self.port}" if self.port else host

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
        self._port = port
        self._address = f"{self.host}:{port}" if port else self.host

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
    def params(self) -> Optional[Dict[str, str]]:
        """
        Gets the query parameters of the URL.

        Returns:
            Optional[Dict[str, str]]: The query parameters of the URL.
        """
        return self._params

    @params.setter
    def params(self, params: Dict[str, str]) -> None:
        """
        Sets the query parameters of the URL.

        Args:
            params (Dict[str, str]): The query parameters to set.
        """
        self._params = params

    def get_param(self, key: str) -> Optional[str]:
        """
        Gets a query parameter from the URL.

        Args:
            key (str): The parameter name.

        Returns:
            str or None: The parameter value. If the parameter does not exist, returns None.
        """
        return self._params.get(key, None) if self._params else None

    def add_param(self, key: str, value: str) -> None:
        """
        Adds a query parameter to the URL.

        Args:
            key (str): The parameter name.
            value (str): The parameter value.
        """
        if not self._params:
            self._params = {}
        self._params[key] = value

    def to_string(self, encode: bool = False) -> str:
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
        # Set Address
        url += self.address if self.address else ""
        # Set path
        url += "/"
        if self.path:
            url += f"{self.path}"
        # Set params
        if self.params:
            url += "?" + "&".join([f"{k}={v}" for k, v in self.params.items()])
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
        return self.to_string()

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
        params = {k: v[0] for k, v in parse.parse_qs(parsed_url.query).items()}
        path = parsed_url.path.lstrip("/")

        return URL(protocol, host, port, username, password, path, params)
