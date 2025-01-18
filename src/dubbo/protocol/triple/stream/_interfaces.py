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

from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.remoting.aio.http2.headers import Http2Headers

__all__ = ["Stream", "ClientStream", "ServerStream"]


class Stream(abc.ABC):
    """
    Stream is a bidirectional channel that manipulates the data flow between peers.
    Inbound data from remote peer is acquired by Stream.Listener.
    Outbound data to remote peer is sent directly by Stream
    """

    @abc.abstractmethod
    def send_headers(self, headers: Http2Headers) -> None:
        """
        Send headers to remote peer
        :param headers: The headers to send
        :type headers: Http2Headers
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_by_local(self, status: TriRpcStatus) -> None:
        """
        Cancel the stream by local
        :param status: The status
        :type status: TriRpcStatus
        """
        raise NotImplementedError()

    class Listener(abc.ABC):
        """
        Listener is a callback interface that receives events on the stream.
        """

        @abc.abstractmethod
        def on_message(self, data: bytes) -> None:
            """
            Called when data is received.
            :param data: The data received
            :type data: bytes
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def on_cancel_by_remote(self, status: TriRpcStatus) -> None:
            """
            Called when the stream is cancelled by remote
            :param status: The status
            :type status: TriRpcStatus
            """
            raise NotImplementedError()


class ClientStream(Stream, abc.ABC):
    """
    ClientStream is used to send request to server and receive response from server.
    """

    @abc.abstractmethod
    def send_message(self, data: bytes, compress_flag: int, last: bool) -> None:
        """
        Send message to remote peer
        :param data: The message data
        :type data: bytes
        :param compress_flag: The compress flag (0: no compress, 1: compress)
        :type compress_flag: int
        :param last: Whether this is the last message
        :type last: bool
        """
        raise NotImplementedError()

    class Listener(Stream.Listener, abc.ABC):
        """
        Listener is a callback interface that receives events on the stream.
        """

        @abc.abstractmethod
        def on_complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
            """
            Called when the stream is completed.
            :param status: The status
            :type status: TriRpcStatus
            :param attachments: The attachments
            :type attachments: Dict[str,Any]
            """
            raise NotImplementedError()


class ServerStream(Stream, abc.ABC):
    """
    ServerStream is used to receive request from client and send response to client.
    """

    @abc.abstractmethod
    def set_compression(self, compression: str) -> None:
        """
        Set the compression.
        :param compression: The compression
        :type compression: str
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def send_message(self, data: bytes, compress_flag: bool) -> None:
        """
        Send message to remote peer
        :param data: The message data
        :type data: bytes
        :param compress_flag: The compress flag
        :type compress_flag: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        """
        Complete the stream
        :param status: The status
        :type status: TriRpcStatus
        :param attachments: The attachments
        :type attachments: Dict[str,Any]
        """
        raise NotImplementedError()

    class Listener(Stream.Listener, abc.ABC):
        """
        Listener is a callback interface that receives events on the stream.
        """

        @abc.abstractmethod
        def on_headers(self, headers: dict[str, Any]) -> None:
            """
            Called when headers are received.
            :param headers: The headers
            :type headers: Http2Headers
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def on_complete(self) -> None:
            """
            Callback when no more data from client side
            """
            raise NotImplementedError()
