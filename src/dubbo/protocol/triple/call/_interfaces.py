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
from typing import Any

from dubbo.protocol.triple.metadata import RequestMetadata
from dubbo.protocol.triple.status import TriRpcStatus

__all__ = ["ClientCall", "ServerCall"]


class ClientCall(abc.ABC):
    """
    Interface for client call.
    """

    @abc.abstractmethod
    def start(self, metadata: RequestMetadata) -> None:
        """
        Start this call.

        :param metadata: call metadata
        :type metadata: RequestMetadata
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def send_message(self, message: Any, last: bool) -> None:
        """
        Send message to server.

        :param message: message to send
        :type message: Any
        :param last: whether this message is the last one
        :type last: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_by_local(self, e: Exception) -> None:
        """
        Cancel this call by local.

        :param e: The exception that caused the call to be canceled
        :type e: Exception
        """
        raise NotImplementedError()

    class Listener(abc.ABC):
        """
        Interface for client call listener.
        """

        @abc.abstractmethod
        def on_message(self, message: Any) -> None:
            """
            Called when a message is received from server.

            :param message: received message
            :type message: Any
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def on_close(self, status: TriRpcStatus, trailers: dict[str, Any]) -> None:
            """
            Called when the call is closed.

            :param status: call status
            :type status: TriRpcStatus
            :param trailers: trailers
            :type trailers: Dict[str, Any]
            """
            raise NotImplementedError()


class ServerCall(abc.ABC):
    """
    Interface for server call.
    """

    @abc.abstractmethod
    def send_message(self, message: Any) -> None:
        """
        Send message to client.

        :param message: message to send
        :type message: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        """
        Complete this call.

        :param status: call status
        :type status: TriRpcStatus
        :param attachments: attachments
        :type attachments: Dict[str, Any]
        """
        raise NotImplementedError()

    class Listener(abc.ABC):
        """
        Interface for server call listener.
        """

        @abc.abstractmethod
        def on_message(self, message: Any, last: bool) -> None:
            """
            Called when a message is received from client.

            :param message: received message
            :type message: Any
            :param last: whether this message is the last one
            :type last: bool
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def on_close(self, status: TriRpcStatus) -> None:
            """
            Called when the call is closed.

            :param status: call status
            :type status: TriRpcStatus
            """
            raise NotImplementedError()
