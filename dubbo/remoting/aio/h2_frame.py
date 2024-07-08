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
import enum
import sys
import time
from typing import Any, Dict, Optional

from h2.events import (DataReceived, Event, RequestReceived, ResponseReceived,
                       StreamReset, TrailersReceived, WindowUpdated)


class H2FrameType(enum.Enum):
    """
    Enum class representing HTTP/2 frame types.
    """

    # Data frame, carries HTTP message bodies.
    DATA = 0x0
    # Headers frame, carries HTTP headers.
    HEADERS = 0x1
    # Priority frame, specifies the priority of a stream.
    PRIORITY = 0x2
    # Reset Stream frame, cancels a stream.
    RST_STREAM = 0x3
    # Settings frame, exchanges configuration parameters.
    SETTINGS = 0x4
    # Push Promise frame, used by the server to push resources.
    PUSH_PROMISE = 0x5
    # Ping frame, measures round-trip time and checks connectivity.
    PING = 0x6
    # Goaway frame, signals that the connection will be closed.
    GOAWAY = 0x7
    # Window Update frame, manages flow control window size.
    WINDOW_UPDATE = 0x8
    # Continuation frame, transmits large header blocks.
    CONTINUATION = 0x9


class H2Frame:
    """
    HTTP/2 frame class. It is used to represent an HTTP/2 frame.
    Args:
        stream_id: The stream identifier.
        frame_type: The frame type.
        data: The data to send. such as: HEADERS: List[Tuple[str, str]], DATA: bytes, END_STREAM: None or bytes.
        end_stream: Whether the stream is ended.
        attributes: The attributes of the frame.
    """

    def __init__(
        self,
        stream_id: int,
        frame_type: H2FrameType,
        data: Any = None,
        end_stream: bool = False,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self._stream_id = stream_id
        self._frame_type = frame_type
        self._data = data
        self._end_stream = end_stream
        self._attributes = attributes or {}

        # The timestamp of the generated frame. -> comparison for Priority Queue
        self._timestamp = int(round(time.time() * 1000))

    @property
    def stream_id(self) -> int:
        return self._stream_id

    @property
    def frame_type(self) -> H2FrameType:
        return self._frame_type

    @property
    def data(self) -> Any:
        return self._data

    @data.setter
    def data(self, data: Any) -> None:
        self._data = data

    @property
    def end_stream(self) -> bool:
        return self._end_stream

    @property
    def attributes(self) -> Dict[str, Any]:
        return self._attributes

    def __lt__(self, other: "H2Frame") -> bool:
        return self._timestamp < other._timestamp

    def __str__(self):
        return (
            f"H2Frame(stream_id={self.stream_id}, "
            f"frame_type={self.frame_type}, "
            f"data={self.data}, "
            f"end_stream={self.end_stream}, "
            f"attributes={self.attributes})"
        )


DATA_COMPLETED_FRAME: H2Frame = H2Frame(0, H2FrameType.DATA, b"")
# Make use of the infinity timestamp to ensure that the DATA_COMPLETED_FRAME is always at the end of the data queue.
DATA_COMPLETED_FRAME._timestamp = sys.maxsize


class H2FrameUtils:
    """
    Utility class for creating HTTP/2 frames.
    """

    @staticmethod
    def create_headers_frame(
        stream_id: int,
        headers: list[tuple[str, str]],
        end_stream: bool = False,
        attributes: Optional[Dict[str, str]] = None,
    ) -> H2Frame:
        """
        Create a headers frame.
        Args:
            stream_id: The stream identifier.
            headers: The headers to send.
            end_stream: Whether the stream is ended.
            attributes: The attributes of the frame.
        Returns:
            The headers frame.
        """
        return H2Frame(stream_id, H2FrameType.HEADERS, headers, end_stream, attributes)

    @staticmethod
    def create_data_frame(
        stream_id: int,
        data: bytes,
        end_stream: bool = False,
        attributes: Optional[Dict[str, str]] = None,
    ) -> H2Frame:
        """
        Create a data frame.
        Args:
            stream_id: The stream identifier.
            data: The data to send.
            end_stream: Whether the stream is ended.
            attributes: The attributes of the frame.
        Returns:
            The data frame.
        """
        return H2Frame(stream_id, H2FrameType.DATA, data, end_stream, attributes)

    @staticmethod
    def create_reset_stream_frame(
        stream_id: int,
        error_code: int,
        attributes: Optional[Dict[str, str]] = None,
    ) -> H2Frame:
        """
        Create a reset stream frame.
        Args:
            stream_id: The stream identifier.
            error_code: The error code.
            attributes: The attributes of the frame.
        Returns:
            The reset stream frame.
        """
        return H2Frame(
            stream_id,
            H2FrameType.RST_STREAM,
            error_code,
            end_stream=True,
            attributes=attributes,
        )

    @staticmethod
    def create_window_update_frame(
        stream_id: int,
        increment: int,
        attributes: Optional[Dict[str, str]] = None,
    ) -> H2Frame:
        """
        Create a window update frame.
        Args:
            stream_id: The stream identifier.
            increment: The increment.
            attributes: The attributes of the frame.
        Returns:
            The window update frame.
        """
        return H2Frame(
            stream_id, H2FrameType.WINDOW_UPDATE, increment, attributes=attributes
        )

    @staticmethod
    def create_frame_by_event(event: Event) -> Optional[H2Frame]:
        """
        Create a frame by the h2.events.Event.
        Args:
            event: The h2.events.Event.
        Returns:
            The H2Frame. None if the event is not supported or not implemented.
        """
        if isinstance(event, (RequestReceived, ResponseReceived)):
            # The headers frame.
            return H2FrameUtils.create_headers_frame(
                event.stream_id, event.headers, event.stream_ended is not None
            )
        elif isinstance(event, TrailersReceived):
            return H2FrameUtils.create_headers_frame(
                event.stream_id, event.headers, end_stream=True
            )
        elif isinstance(event, DataReceived):
            # The data frame.
            return H2FrameUtils.create_data_frame(
                event.stream_id,
                event.data,
                end_stream=event.stream_ended is not None,
                attributes={"flow_controlled_length": event.flow_controlled_length},
            )
        elif isinstance(event, StreamReset):
            # The reset stream frame.
            return H2FrameUtils.create_reset_stream_frame(
                event.stream_id, event.error_code
            )
        elif isinstance(event, WindowUpdated):
            # The window update frame.
            return H2FrameUtils.create_window_update_frame(event.stream_id, event.delta)
