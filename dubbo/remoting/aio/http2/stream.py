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
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from dubbo.remoting.aio.exceptions import StreamError
from dubbo.remoting.aio.http2.frames import (
    DataFrame,
    HeadersFrame,
    ResetStreamFrame,
    UserActionFrames,
)
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode

__all__ = ["Http2Stream", "DefaultHttp2Stream"]


class Http2Stream(abc.ABC):
    """
    A "stream" is an independent, bidirectional sequence of frames exchanged between the client and server within an HTTP/2 connection.
    see: https://datatracker.ietf.org/doc/html/rfc7540#section-5
    """

    __slots__ = ["_id", "_listener", "_local_closed", "_remote_closed"]

    def __init__(self, stream_id: int, listener: "Http2Stream.Listener"):
        self._id = stream_id

        self._listener = listener
        self._listener.bind(self)

        # Whether the stream is closed locally. -> it means the stream can't send any more frames.
        self._local_closed = False
        # Whether the stream is closed remotely. -> it means the stream can't receive any more frames.
        self._remote_closed = False

    @property
    def id(self) -> int:
        """
        Get the stream identifier.
        """
        return self._id

    @property
    def listener(self) -> "Http2Stream.Listener":
        """
        Get the listener.
        """
        return self._listener

    @property
    def local_closed(self) -> bool:
        """
        Check if the stream is closed locally.
        """
        return self._local_closed

    @property
    def remote_closed(self) -> bool:
        """
        Check if the stream is closed remotely.
        """
        return self._remote_closed

    def close_local(self) -> None:
        """
        Close the stream locally.
        """
        if self._local_closed:
            return
        self._local_closed = True

    def close_remote(self) -> None:
        """
        Close the stream remotely.
        """
        if self._remote_closed:
            return
        self._remote_closed = True

    @abc.abstractmethod
    def send_headers(self, headers: Http2Headers, end_stream: bool = False) -> None:
        """
        Send the headers.
        :param headers: The HTTP/2 headers.
                        The second send of headers will be treated as trailers (end_stream must be True).
        :type headers: Http2Headers
        :param end_stream: Whether to close the stream after sending the data.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def send_data(self, data: bytes, end_stream: bool = False) -> None:
        """
        Send the data.
        :param data: The data to send.
        :type data: bytes
        :param end_stream: Whether to close the stream after sending the data.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_by_local(self, error_code: Http2ErrorCode) -> None:
        """
        Cancel the stream locally. -> send RST_STREAM frame.
        :param error_code: The error code.
        :type error_code: Http2ErrorCode
        """
        raise NotImplementedError()

    class Listener(abc.ABC):
        """
        Http2StreamListener is a base class for handling events in an HTTP/2 stream.

        This class provides a set of callback methods that are called when specific
        events occur on the stream, such as receiving headers, receiving data, or
        resetting the stream. To use this class, create a subclass and implement the
        callback methods for the events you want to handle.
        """

        __slots__ = ["_stream"]

        def __init__(self):
            self._stream: Optional["Http2Stream"] = None

        def bind(self, stream: "Http2Stream") -> None:
            """
            Bind the stream to the listener.
            :param stream: The stream to bind.
            :type stream: Http2Stream
            """
            self._stream = stream

        @property
        def stream(self) -> "Http2Stream":
            """
            Get the stream.
            """
            return self._stream

        @abc.abstractmethod
        def on_headers(self, headers: Http2Headers, end_stream: bool) -> None:
            """
            Called when the headers are received.
            :param headers: The HTTP/2 headers.
            :type headers: Http2Headers
            :param end_stream: Whether the stream is closed after receiving the headers.
            :type end_stream: bool
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def on_data(self, data: bytes, end_stream: bool) -> None:
            """
            Called when the data is received.
            :param data: The data.
            :type data: bytes
            :param end_stream: Whether the stream is closed after receiving the data.
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def cancel_by_remote(self, error_code: Http2ErrorCode) -> None:
            """
            Cancel the stream remotely.
            :param error_code: The error code.
            :type error_code: Http2ErrorCode
            """
            raise NotImplementedError()


class DefaultHttp2Stream(Http2Stream):
    """
    Default implementation of the Http2Stream.
    """

    __slots__ = [
        "_loop",
        "_protocol",
        "_inbound_controller",
        "_outbound_controller",
        "_headers_sent",
    ]

    def __init__(
        self,
        stream_id: int,
        listener: "Http2Stream.Listener",
        loop: asyncio.AbstractEventLoop,
        protocol,
        executor: Optional[ThreadPoolExecutor] = None,
    ):
        # Avoid circular import
        from dubbo.remoting.aio.http2.controllers import (
            FrameInboundController,
            FrameOutboundController,
        )

        super().__init__(stream_id, listener)
        self._loop = loop
        self._protocol = protocol

        # steam inbound controller
        self._inbound_controller: FrameInboundController = FrameInboundController(
            self, self._loop, self._protocol, executor
        )
        # steam outbound controller
        self._outbound_controller: FrameOutboundController = FrameOutboundController(
            self, self._loop, self._protocol
        )

        # The flag to indicate whether the headers have been sent.
        self._headers_sent = False

    def close_local(self) -> None:
        super().close_local()
        self._outbound_controller.close()

    def close_remote(self) -> None:
        super().close_remote()
        self._inbound_controller.close()

    def send_headers(self, headers: Http2Headers, end_stream: bool = False) -> None:
        if self.local_closed:
            raise StreamError("The stream has been closed locally.")
        elif self._headers_sent and not end_stream:
            raise StreamError(
                "Trailers must be the last frame of the stream(end_stream must be True)."
            )

        self._headers_sent = True
        headers_frame = HeadersFrame(self.id, headers, end_stream=end_stream)
        self._outbound_controller.write_headers(headers_frame)

    def send_data(self, data: bytes, end_stream: bool = False) -> None:
        if self.local_closed:
            raise StreamError("The stream has been closed locally.")
        elif not self._headers_sent:
            raise StreamError("Headers have not been sent.")
        data_frame = DataFrame(self.id, data, len(data), end_stream=end_stream)
        self._outbound_controller.write_data(data_frame)

    def cancel_by_local(self, error_code: Http2ErrorCode) -> None:
        if self.local_closed:
            raise StreamError("The stream has been closed locally.")
        reset_frame = ResetStreamFrame(self.id, error_code)
        self._outbound_controller.write_rst(reset_frame)

    def receive_frame(self, frame: UserActionFrames) -> None:
        """
        Receive the frame.
        :param frame: The frame to receive.
        :type frame: UserActionFrames
        """
        self._inbound_controller.write_frame(frame)
