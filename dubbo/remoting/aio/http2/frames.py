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
import time

from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode, Http2FrameType


class Http2Frame:
    """
    HTTP/2 frame class. It is used to represent an HTTP/2 frame.
    Args:
        stream_id: The stream identifier.
        frame_type: The frame type.
    """

    def __init__(
        self,
        stream_id: int,
        frame_type: Http2FrameType,
        end_stream: bool = False,
    ):
        self.stream_id = stream_id
        self.frame_type = frame_type
        self.end_stream = end_stream

        # The timestamp of the generated frame. -> comparison for Priority Queue
        self.timestamp = int(round(time.time() * 1000))

    def __lt__(self, other: "Http2Frame") -> bool:
        return self.timestamp <= other.timestamp

    def __repr__(self) -> str:
        return f"<Http2Frame stream_id={self.stream_id} frame_type={self.frame_type} end_stream={self.end_stream}>"


class HeadersFrame(Http2Frame):
    """
    HTTP/2 headers frame.
    Args:
        stream_id: The stream identifier.
        headers: The HTTP/2 headers.
        end_stream: Whether the stream is ended.
    """

    def __init__(
        self,
        stream_id: int,
        headers: Http2Headers,
        end_stream: bool = False,
    ):
        super().__init__(stream_id, Http2FrameType.HEADERS, end_stream)
        self.headers = headers

    def __repr__(self) -> str:
        return f"<HeadersFrame stream_id={self.stream_id} headers={self.headers.to_list()} end_stream={self.end_stream}>"


class DataFrame(Http2Frame):
    """
    HTTP/2 data frame.
    Args:
        stream_id: The stream identifier.
        data: The data to send.
        data_length: The amount of data received that counts against the flow control window.
        end_stream: Whether the stream
    """

    def __init__(
        self,
        stream_id: int,
        data: bytes,
        data_length: int,
        end_stream: bool = False,
    ):
        super().__init__(stream_id, Http2FrameType.DATA, end_stream)
        self.data = data
        self.data_length = data_length

    def __repr__(self) -> str:
        return f"<DataFrame stream_id={self.stream_id} data={self.data} end_stream={self.end_stream}>"


class WindowUpdateFrame(Http2Frame):
    """
    HTTP/2 window update frame.
    Args:
        stream_id: The stream identifier.
        delta: The number of bytes by which to increase the flow control window.
    """

    def __init__(
        self,
        stream_id: int,
        delta: int,
    ):
        super().__init__(stream_id, Http2FrameType.WINDOW_UPDATE, False)
        self.delta = delta

    def __repr__(self) -> str:
        return f"<WindowUpdateFrame stream_id={self.stream_id} delta={self.delta}>"


class ResetStreamFrame(Http2Frame):
    """
    HTTP/2 reset stream frame.
    Args:
        stream_id: The stream identifier.
        error_code: The error code that indicates the reason for closing the stream.
    """

    def __init__(
        self,
        stream_id: int,
        error_code: Http2ErrorCode,
    ):
        super().__init__(stream_id, Http2FrameType.RST_STREAM, True)
        self.error_code = error_code

    def __repr__(self) -> str:
        return f"<ResetStreamFrame stream_id={self.stream_id} error_code={self.error_code}>"
