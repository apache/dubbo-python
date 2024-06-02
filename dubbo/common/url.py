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

import urllib.parse as ulp


class URL:

    def __init__(self,
                 protocol: str,
                 host: str,
                 port: int,
                 username: str = None,
                 password: str = None,
                 path: str = None,
                 params: dict[str, str] = None
                 ):
        """
        Initialize URL object.
        :param protocol: protocols.
        :param host: host.
        :param port: port.
        :param username: username.
        :param password: password.
        :param path: path.
        :param params: parameters.
        """
        self.protocol = protocol
        self.host = host
        self.port = port
        self.username = username
        if password and not username:
            raise ValueError("Password must be set with username.")
        self.password = password
        self.path = path or ''
        self.params = params or {}

    def to_str(self, encoded: bool = False) -> str:
        """
        Convert URL object to URL string.
        :param encoded: Whether to encode the URL, default is False.
        """
        # Set username and password
        auth_part = f"{self.username}:{self.password}@" if self.username or self.password else ""
        # Set location
        netloc = f"{auth_part}{self.host}{':' + str(self.port) if self.port else ''}"
        query = ulp.urlencode(self.params)
        path = self.path

        url_parts = (self.protocol, netloc, path, '', query, '')
        url_str = str(ulp.urlunparse(url_parts))

        if encoded:
            url_str = ulp.quote(url_str)

        return url_str

    def __str__(self):
        return self.to_str()


def parse_url(url: str, encoded: bool = False) -> URL:
    """
    Parse URL string to URL object.
    :param url: URL string.
    :param encoded: Whether the URL is encoded, default is False.
    :return: URL
    """
    if encoded:
        url = ulp.unquote(url)
    parsed_url = ulp.urlparse(url)
    protocol = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port
    path = parsed_url.path
    params = {k: v[0] for k, v in ulp.parse_qs(parsed_url.query).items()}
    username = parsed_url.username or ''
    password = parsed_url.password or ''
    return URL(protocol, host, port, username, password, path, params)
