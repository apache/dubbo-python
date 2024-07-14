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
import concurrent
from typing import List, Optional, Tuple, Union

from h2.config import H2Configuration
from h2.connection import H2Connection

from dubbo.constants import common_constants
from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.exceptions import ProtocolException
from dubbo.remoting.aio.http2.controllers import FollowController
from dubbo.remoting.aio.http2.frames import Http2Frame
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import Http2Stream
from dubbo.remoting.aio.http2.utils import Http2EventUtils
from dubbo.url import URL

logger = loggerFactory.get_logger(__name__)


class Http2Protocol(asyncio.Protocol):

    def __init__(self, url: URL):
        self._url = url
        self._loop = asyncio.get_running_loop()

        # Create the H2 state machine
        side_client = (
            self._url.get_parameter(common_constants.TRANSPORTER_SIDE_KEY)
            == common_constants.TRANSPORTER_SIDE_CLIENT
        )
        h2_config = H2Configuration(client_side=side_client, header_encoding="utf-8")
        self._h2_connection: H2Connection = H2Connection(config=h2_config)

        # The transport instance
        self._transport: Optional[asyncio.Transport] = None

        self._follow_controller: Optional[FollowController] = None

        self._stream_handler = self._url.attributes[
            common_constants.TRANSPORTER_STREAM_HANDLER_KEY
        ]

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
        self._transport.write(self._h2_connection.data_to_send())

        # Create and start the follow controller
        self._follow_controller = FollowController(
            self._loop, self._h2_connection, self._transport
        )
        self._follow_controller.start()

        # Initialize the stream handler
        self._stream_handler.do_init(self._loop, self)

        # Notify the connection is established
        if event := self._url.attributes.get("connect-event"):
            event.set()

    def get_next_stream_id(
        self, future: Union[asyncio.Future, concurrent.futures.Future]
    ) -> None:
        """
        Create a new stream.(thread-safe)
        Args:
            future: The future to set the stream identifier.
        """

        def _inner_operation(_future: Union[asyncio.Future, concurrent.futures.Future]):
            stream_id = self._h2_connection.get_next_available_stream_id()
            _future.set_result(stream_id)

        self._loop.call_soon_threadsafe(_inner_operation, future)

    def write(self, frame: Http2Frame, stream: Http2Stream) -> asyncio.Event:
        """
        Send the HTTP/2 frame.(thread-safe)
        Args:
            frame: The HTTP/2 frame.
            stream: The HTTP/2 stream.
        Returns:
            The event to be set after sending the frame.
        """
        event = asyncio.Event()
        self._loop.call_soon_threadsafe(self._send_frame, frame, stream, event)
        return event

    def _send_frame(self, frame: Http2Frame, stream: Http2Stream, event: asyncio.Event):
        """
        Send the HTTP/2 frame.(thread-unsafe)
        Args:
            frame: The HTTP/2 frame.
            stream: The HTTP/2 stream.
            event: The event to be set after sending the frame.
        """
        frame_type = frame.frame_type
        if frame_type == Http2FrameType.HEADERS:
            self._send_headers_frame(
                frame.stream_id, frame.headers.to_list(), frame.end_stream, event
            )
        elif frame_type == Http2FrameType.DATA:
            self._follow_controller.send_data(
                stream, frame.data, frame.end_stream, event
            )
        elif frame_type == Http2FrameType.RST_STREAM:
            self._send_reset_frame(frame.stream_id, frame.error_code.value, event)
        else:
            logger.warning(f"Unhandled frame: {frame}")

    def _send_headers_frame(
        self,
        stream_id: int,
        headers: List[Tuple[str, str]],
        end_stream: bool,
        event: Optional[asyncio.Event] = None,
    ):
        """
        Send the HTTP/2 headers frame.(thread-unsafe)
        Args:
            stream_id: The stream identifier.
            headers: The headers to send.
            end_stream: Whether the stream is ended.
            event: The event to be set after sending the frame.
        """
        self._h2_connection.send_headers(stream_id, headers, end_stream=end_stream)
        self._transport.write(self._h2_connection.data_to_send())
        if event:
            event.set()

    def _send_reset_frame(
        self, stream_id: int, error_code: int, event: Optional[asyncio.Event] = None
    ):
        """
        Send the HTTP/2 reset frame.(thread-unsafe)
        Args:
            stream_id: The stream identifier.
            error_code: The error code.
            event: The event to be set after sending the frame
        """
        self._h2_connection.reset_stream(stream_id, error_code)
        self._transport.write(self._h2_connection.data_to_send())
        if event:
            event.set()

    def data_received(self, data):
        events = self._h2_connection.receive_data(data)
        # Process the event
        try:
            for event in events:
                frame = Http2EventUtils.convert_to_frame(event)
                if frame is not None:
                    if frame.frame_type == Http2FrameType.WINDOW_UPDATE:
                        # Because flow control may be at the connection level, it is handled here
                        self._follow_controller.increment_flow_control_window(
                            frame.stream_id
                        )
                    else:
                        self._stream_handler.handle_frame(frame)

                # If frame is None, there are two possible cases:
                # 1. Events that are handled automatically by the H2 library (e.g. RemoteSettingsChanged, PingReceived).
                #    -> We just need to send it.
                # 2. Events that are not implemented or do not require attention. -> We'll ignore it for now.
                if outbound_data := self._h2_connection.data_to_send():
                    self._transport.write(outbound_data)

        except Exception as e:
            raise ProtocolException("Failed to process the Http/2 event.") from e

    def close(self):
        """
        Close the connection.
        """
        self._h2_connection.close_connection()
        self._transport.write(self._h2_connection.data_to_send())

        self._transport.close()

    def connection_lost(self, exc):
        """
        Called when the connection is lost.
        """
        self._follow_controller.stop()
        # Notify the connection is established
        if future := self._url.attributes.get("close-future"):
            if exc:
                future.set_exception(exc)
            else:
                future.set_result(None)
