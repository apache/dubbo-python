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
from dubbo.url import URL


class Client:

    def __init__(self, url: URL):
        self._url = url

    def is_connected(self) -> bool:
        """
        Check if the client is connected.
        """
        raise NotImplementedError("is_connected() is not implemented.")

    def is_closed(self) -> bool:
        """
        Check if the client is closed.
        """
        raise NotImplementedError("is_closed() is not implemented.")

    def connect(self):
        """
        Connect to the server.
        """
        raise NotImplementedError("connect() is not implemented.")

    def reconnect(self):
        """
        Reconnect to the server.
        """
        raise NotImplementedError("reconnect() is not implemented.")

    def close(self):
        """
        Close the client.
        """
        raise NotImplementedError("close() is not implemented.")


class Server:
    # TODO define the interface of the server.
    pass


class Transporter:

    def connect(self, url: URL) -> Client:
        """
        Connect to a server.
        """
        raise NotImplementedError("connect() is not implemented.")

    def bind(self, url: URL) -> Server:
        """
        Bind a server.
        """
        raise NotImplementedError("bind() is not implemented.")
