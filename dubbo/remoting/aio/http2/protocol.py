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
from typing import List, Optional, Tuple

from h2.config import H2Configuration
from h2.connection import H2Connection

from dubbo.constants import common_constants
from dubbo.loggers import loggerFactory
from dubbo.remoting.aio import constants as h2_constants
from dubbo.remoting.aio.exceptions import ProtocolError
from dubbo.remoting.aio.http2.controllers import RemoteFlowController
from dubbo.remoting.aio.http2.frames import UserActionFrames
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import Http2Stream
from dubbo.remoting.aio.http2.utils import Http2EventUtils
from dubbo.url import URL
from dubbo.utils import EventHelper, FutureHelper

__all__ = ["Http2Protocol"]

_LOGGER = loggerFactory.get_logger()


class Http2Protocol(asyncio.Protocol):
    """
    HTTP/2 protocol implementation.
    """

    __slots__ = [
        "_url",
        "_loop",
        "_h2_connection",
        "_transport",
        "_flow_controller",
        "_stream_handler",
    ]

    def __init__(self, url: URL):
        self._url = url
        self._loop = asyncio.get_running_loop()

        # Create the H2 state machine
        side_client = (
            self._url.parameters.get(common_constants.SIDE_KEY)
            == common_constants.CLIENT_VALUE
        )
        h2_config = H2Configuration(client_side=side_client, header_encoding="utf-8")
        self._h2_connection: H2Connection = H2Connection(config=h2_config)

        # The transport instance
        self._transport: Optional[asyncio.Transport] = None

        self._flow_controller: Optional[RemoteFlowController] = None

        self._stream_handler = self._url.attributes[h2_constants.STREAM_HANDLER_KEY]

    def connection_made(self, transport: asyncio.Transport):
        """
        Called when the connection is first established. We complete the following actions:
        1. Save the transport.
        2. Initialize the H2 connection.
        3. Create and start the follow controller.
        4. Initialize the stream handler.
        """
        self._transport = transport
        self._h2_connection.initiate_connection()
        self._flush()

        # Create and start the follow controller
        self._flow_controller = RemoteFlowController(
            self._h2_connection, self._transport, self._loop
        )

        # Initialize the stream handler
        self._stream_handler.do_init(self._loop, self)

    def get_next_stream_id(self, future) -> None:
        """
        Create a new stream.(thread-safe)
        :param future: The future to set the stream identifier.
        """

        def _inner_operation(_future):
            stream_id = self._h2_connection.get_next_available_stream_id()
            FutureHelper.set_result(_future, stream_id)

        self._loop.call_soon_threadsafe(_inner_operation, future)

    def send_frame(
        self,
        frame: UserActionFrames,
        stream: Http2Stream,
        event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Send the HTTP/2 frame.(thread-unsafe)
        :param frame: The frame to send.
        :type frame: UserActionFrames
        :param stream: The stream.
        :type stream: Http2Stream
        :param event: The event to be set after sending the frame.
        :type event: Optional[asyncio.Event]
        """
        frame_type = frame.frame_type
        if frame_type == Http2FrameType.HEADERS:
            self._send_headers_frame(
                frame.stream_id, frame.headers.to_list(), frame.end_stream, event
            )
        elif frame_type == Http2FrameType.DATA:
            self._flow_controller.write_data(stream, frame, event)
        elif frame_type == Http2FrameType.RST_STREAM:
            self._send_reset_frame(frame.stream_id, frame.error_code.value, event)
        else:
            _LOGGER.warning(f"Unhandled frame: {frame}")

    def _send_headers_frame(
        self,
        stream_id: int,
        headers: List[Tuple[str, str]],
        end_stream: bool,
        event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Send the HTTP/2 headers frame.(thread-unsafe)
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param headers: The headers.
        :type headers: List[Tuple[str, str]]
        :param end_stream: Whether the stream is ended.
        :type end_stream: bool
        :param event: The event to be set after sending the frame.
        """
        self._h2_connection.send_headers(stream_id, headers, end_stream=end_stream)
        self._flush()
        EventHelper.set(event)

    def _flush(self) -> None:
        """
        Flush the data to the transport.
        """
        outbound_data = self._h2_connection.data_to_send()
        if outbound_data != b"":
            self._transport.write(outbound_data)

    def _send_reset_frame(
        self, stream_id: int, error_code: int, event: Optional[asyncio.Event] = None
    ) -> None:
        """
        Send the HTTP/2 reset frame.(thread-unsafe)
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param error_code: The error code.
        :type error_code: int
        :param event: The event to be set after sending the frame.
        :type event: Optional[asyncio.Event]
        """
        self._h2_connection.reset_stream(stream_id, error_code)
        self._flush()
        EventHelper.set(event)

    def data_received(self, data):
        """
        Called when some data is received from the transport.
        :param data: The data received.
        :type data: bytes
        """
        events = self._h2_connection.receive_data(data)
        # Process the event
        try:
            for event in events:
                frame = Http2EventUtils.convert_to_frame(event)
                if frame is not None:
                    if frame.frame_type == Http2FrameType.WINDOW_UPDATE:
                        # Because flow control may be at the connection level, it is handled here
                        self._flow_controller.release_flow_control(frame)
                    else:
                        self._stream_handler.handle_frame(frame)

                # If frame is None, there are two possible cases:
                # 1. Events that are handled automatically by the H2 library (e.g. RemoteSettingsChanged, PingReceived).
                #    -> We just need to send it.
                # 2. Events that are not implemented or do not require attention. -> We'll ignore it for now.
                self._flush()

        except Exception as e:
            raise ProtocolError("Failed to process the Http/2 event.") from e

    def ack_received_data(self, stream_id: int, ack_length: int) -> None:
        """
        Acknowledge the received data.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param ack_length: The length of the data to acknowledge.
        :type ack_length: int
        """

        self._h2_connection.acknowledge_received_data(ack_length, stream_id)
        self._flush()

    def close(self):
        """
        Close the connection.
        """
        self._h2_connection.close_connection()
        self._flush()
        self._transport.close()

    def connection_lost(self, exc):
        """
        Called when the connection is lost.
        """
        self._flow_controller.close()
        # Notify the connection is established
        future = self._url.attributes.get(h2_constants.CLOSE_FUTURE_KEY)
        if future:
            if exc:
                FutureHelper.set_exception(future, exc)
            else:
                FutureHelper.set_result(future, None)
