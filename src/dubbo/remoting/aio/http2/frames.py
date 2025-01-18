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

from typing import Union

from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode, Http2FrameType

__all__ = [
    "Http2Frame",
    "HeadersFrame",
    "DataFrame",
    "WindowUpdateFrame",
    "RstStreamFrame",
    "PingFrame",
    "UserActionFrames",
]


class Http2Frame:
    """
    HTTP/2 frame class. It is used to represent an HTTP/2 frame.
    """

    __slots__ = ["stream_id", "frame_type", "end_stream", "timestamp"]

    def __init__(
        self,
        stream_id: int,
        frame_type: Http2FrameType,
        end_stream: bool = False,
    ):
        """
        Initialize the HTTP/2 frame.
        :param stream_id: The stream identifier. 0 for connection-level frames.
        :type stream_id: int
        :param frame_type: The frame type.
        :type frame_type: Http2FrameType
        :param end_stream: Whether the stream is ended.
        :type end_stream: bool
        """
        self.stream_id = stream_id
        self.frame_type = frame_type
        self.end_stream = end_stream

    def __repr__(self) -> str:
        return f"<Http2Frame stream_id={self.stream_id} frame_type={self.frame_type} end_stream={self.end_stream}>"


class HeadersFrame(Http2Frame):
    """
    HTTP/2 headers frame.
    """

    __slots__ = ["headers"]

    def __init__(
        self,
        stream_id: int,
        headers: Http2Headers,
        end_stream: bool = False,
    ):
        """
        Initialize the HTTP/2 headers frame.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param headers: The headers to send.
        :type headers: Http2Headers
        :param end_stream: Whether the stream is ended.
        :type end_stream: bool
        """
        super().__init__(stream_id, Http2FrameType.HEADERS, end_stream)
        self.headers = headers

    def __repr__(self) -> str:
        return (
            f"<HeadersFrame stream_id={self.stream_id} headers={self.headers.to_list()} end_stream={self.end_stream}>"
        )


class DataFrame(Http2Frame):
    """
    HTTP/2 data frame.
    """

    __slots__ = ["data", "padding"]

    def __init__(
        self,
        stream_id: int,
        data: bytes,
        length: int,
        end_stream: bool = False,
    ):
        """
        Initialize the HTTP/2 data frame.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param data: The data to send.
        :type data: bytes
        :param length: The length of the data.
        :type length: int
        :param end_stream: Whether the stream is ended.
        """
        super().__init__(stream_id, Http2FrameType.DATA, end_stream)
        self.data = data
        self.padding = length

    def __repr__(self) -> str:
        return f"<DataFrame stream_id={self.stream_id} data={self.data} end_stream={self.end_stream}>"


class WindowUpdateFrame(Http2Frame):
    """
    HTTP/2 window update frame.
    """

    __slots__ = ["delta"]

    def __init__(
        self,
        stream_id: int,
        delta: int,
    ):
        """
        Initialize the HTTP/2 window update frame.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param delta: The delta value.
        :type delta: int
        """
        super().__init__(stream_id, Http2FrameType.WINDOW_UPDATE, False)
        self.delta = delta

    def __repr__(self) -> str:
        return f"<WindowUpdateFrame stream_id={self.stream_id} delta={self.delta}>"


class RstStreamFrame(Http2Frame):
    """
    HTTP/2 reset stream frame.
    """

    __slots__ = ["error_code"]

    def __init__(
        self,
        stream_id: int,
        error_code: Http2ErrorCode,
    ):
        """
        Initialize the HTTP/2 reset stream frame.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param error_code: The error code.
        :type error_code: Http2ErrorCode
        """
        super().__init__(stream_id, Http2FrameType.RST_STREAM, True)
        self.error_code = error_code

    def __repr__(self) -> str:
        return f"<RstStreamFrame stream_id={self.stream_id} error_code={self.error_code}>"


class PingFrame(Http2Frame):
    """
    HTTP/2 ping frame.
    """

    __slots__ = ["data", "ack"]

    def __init__(self, data: bytes, ack: bool = False):
        """
        Initialize the HTTP/2 ping frame.
        :param data: The data.
        :type data: bytes
        """
        super().__init__(0, Http2FrameType.PING, False)
        self.data = data
        self.ack = ack

    def __repr__(self) -> str:
        return f"<PingFrame data={self.data}>"


# User action frames.
UserActionFrames = Union[HeadersFrame, DataFrame, RstStreamFrame]
