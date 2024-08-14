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

import abc

from dubbo.url import URL

__all__ = ["Client", "Server", "Transporter"]


class Client(abc.ABC):

    def __init__(self, url: URL):
        self._url = url

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the client is connected.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def is_closed(self) -> bool:
        """
        Check if the client is closed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def connect(self):
        """
        Connect to the server.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def reconnect(self):
        """
        Reconnect to the server.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def close(self):
        """
        Close the client.
        """
        raise NotImplementedError()


class Server:
    """
    Server
    """

    @abc.abstractmethod
    def is_exported(self) -> bool:
        """
        Check if the server is exported.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def is_closed(self) -> bool:
        """
        Check if the server is closed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def export(self):
        """
        Export the server.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def close(self):
        """
        Close the server.
        """
        raise NotImplementedError()


class Transporter(abc.ABC):
    """
    Transporter interface
    """

    @abc.abstractmethod
    def connect(self, url: URL) -> Client:
        """
        Connect to a server.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def bind(self, url: URL) -> Server:
        """
        Bind a server.
        """
        raise NotImplementedError()
