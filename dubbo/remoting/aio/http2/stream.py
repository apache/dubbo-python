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
import asyncio
from typing import Optional

from dubbo.remoting.aio.exceptions import StreamException
from dubbo.remoting.aio.http2.frames import (
    DataFrame,
    HeadersFrame,
    Http2Frame,
    ResetStreamFrame,
)
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode, Http2FrameType


class Http2Stream:
    """
    A "stream" is an independent, bidirectional sequence of frames exchanged between the client and server within an HTTP/2 connection.
    see: https://datatracker.ietf.org/doc/html/rfc7540#section-5
    Args:
        stream_id: The stream identifier.
        listener: The stream listener.
        loop: The asyncio event loop.
        protocol: The HTTP/2 protocol.
    """

    def __init__(
        self,
        stream_id: int,
        listener: "StreamListener",
        loop: asyncio.AbstractEventLoop,
        protocol,
    ):
        from dubbo.remoting.aio.http2.controllers import FrameOrderController
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        self._loop: asyncio.AbstractEventLoop = loop
        self._protocol: Http2Protocol = protocol

        # The stream identifier.
        self._id = stream_id

        self._listener = listener

        # The frame order controller.
        self._frame_order_controller: FrameOrderController = FrameOrderController(
            self, self._loop, self._protocol
        )
        self._frame_order_controller.start()

        # Whether the headers have been sent.
        self._headers_sent = False
        # Whether the headers have been received.
        self._headers_received = False

        # Indicates whether the frame identified with end_stream was written (and may not have been sent yet).
        self._end_stream = False

        # Whether the stream is closed locally or remotely.
        self._local_closed = False
        self._remote_closed = False

    @property
    def id(self) -> int:
        return self._id

    def is_headers_sent(self) -> bool:
        return self._headers_sent

    def is_local_closed(self) -> bool:
        """
        Check if the stream is closed locally.
        """
        return self._local_closed

    def close_local(self) -> None:
        """
        Close the stream locally.
        """
        self._local_closed = True
        self._frame_order_controller.stop()

    def is_remote_closed(self) -> bool:
        """
        Check if the stream is closed remotely.
        """
        return self._remote_closed

    def close_remote(self) -> None:
        """
        Close the stream remotely.
        """
        self._remote_closed = True

    def _send_available(self):
        """
        Check if the stream is available for sending frames.
        """
        return not self.is_local_closed() and not self._end_stream

    def send_headers(self, headers: Http2Headers, end_stream: bool = False) -> None:
        """
        Send the headers.(thread-unsafe)
        Args:
            headers: The HTTP/2 headers.
            end_stream: Whether to close the stream after sending the data.
        """
        if self.is_headers_sent():
            raise StreamException("Headers have been sent.")
        elif not self._send_available():
            raise StreamException(
                "The stream cannot send a frame because it has been closed."
            )

        headers_frame = HeadersFrame(self.id, headers, end_stream=end_stream)
        self._end_stream = end_stream
        self._frame_order_controller.write_headers(headers_frame)

        self._headers_sent = True

    def send_data(
        self, data: bytes, end_stream: bool = False, last: bool = False
    ) -> None:
        """
        Send the data.(thread-unsafe)
        Args:
            data: The data to send.
            end_stream: Whether to close the stream after sending the data.
            last: Is it the last data frame?
        """
        if not self.is_headers_sent():
            raise StreamException("Headers have not been sent.")
        elif not self._send_available():
            raise StreamException(
                "The stream cannot send a frame because it has been closed."
            )

        data_frame = DataFrame(self.id, data, len(data), end_stream=end_stream)
        self._end_stream = end_stream
        self._frame_order_controller.write_data(data_frame, last)

    def send_trailers(self, headers: Http2Headers, send_data: bool) -> None:
        """
        Send trailers with the given headers. Optionally, indicate if data frames
        need to be sent.

        Args:
            headers: The HTTP/2 headers to be sent as trailers.
            send_data: A flag indicating whether data frames need to be sent.
        """
        if not self.is_headers_sent():
            raise StreamException("Headers have not been sent.")
        elif not self._send_available():
            raise StreamException(
                "The stream cannot send a frame because it has been closed."
            )

        trailers_frame = HeadersFrame(self.id, headers, end_stream=True)
        self._end_stream = True
        if send_data:
            self._frame_order_controller.write_trailers_after_data(trailers_frame)
        else:
            self._frame_order_controller.write_trailers(trailers_frame)

    def send_reset(self, error_code: Http2ErrorCode) -> None:
        """
        Send the reset frame.(thread-unsafe)
        Args:
            error_code: The error code.
        """
        if self.is_local_closed():
            raise StreamException("The stream has been reset.")

        reset_frame = ResetStreamFrame(self.id, error_code)
        # It's a special frame, no need to queue, just send it
        self._protocol.write(reset_frame, self)
        # close the stream locally and remotely
        self.close_local()
        self.close_remote()

    def receive_frame(self, frame: Http2Frame) -> None:
        """
        Receive a frame from the stream.
        Args:
            frame: The frame to be received.
        """
        if self.is_remote_closed():
            # The stream is closed remotely, ignore the frame
            return

        if frame.end_stream:
            # received end_stream frame, close the stream remotely
            self.close_remote()

        frame_type = frame.frame_type
        if frame_type == Http2FrameType.HEADERS:
            if not self._headers_received:
                # HEADERS frame
                self._headers_received = True
                self._listener.on_headers(frame.headers, frame.end_stream)
            else:
                # TRAILERS frame
                self._listener.on_trailers(frame.headers)
        elif frame_type == Http2FrameType.DATA:
            self._listener.on_data(frame.data, frame.end_stream)
        elif frame_type == Http2FrameType.RST_STREAM:
            self._listener.on_reset(frame.error_code)
            self.close_local()


class StreamListener:
    """
    Http2StreamListener is a base class for handling events in an HTTP/2 stream.

    This class provides a set of callback methods that are called when specific
    events occur on the stream, such as receiving headers, receiving data, or
    resetting the stream. To use this class, create a subclass and implement the
    callback methods for the events you want to handle.
    """

    def __init__(self):
        self._stream: Optional[Http2Stream] = None

    def bind(self, stream: Http2Stream) -> None:
        """
        Bind the stream to the listener.
        Args:
            stream: The stream.
        """
        self._stream = stream

    def on_headers(self, headers: Http2Headers, end_stream: bool) -> None:
        """
        Called when the headers are received.
        Args:
            headers: The HTTP/2 headers.
            end_stream: Whether the stream is closed after receiving the headers.
        """
        raise NotImplementedError("on_headers() is not implemented.")

    def on_data(self, data: bytes, end_stream: bool) -> None:
        """
        Called when the data is received.
        Args:
            data: The data.
            end_stream: Whether the stream is closed after receiving the data.
        """
        raise NotImplementedError("on_data() is not implemented.")

    def on_trailers(self, headers: Http2Headers) -> None:
        """
        Called when the trailers are received.
        Args:
            headers: The HTTP/2 headers.
        """
        raise NotImplementedError("on_trailers() is not implemented.")

    def on_reset(self, error_code: Http2ErrorCode) -> None:
        """
        Called when the stream is reset.
        Args:
            error_code: The error code.
        """
        raise NotImplementedError("on_reset() is not implemented.")
