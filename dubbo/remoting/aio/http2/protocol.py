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
import struct
import time
from typing import Optional

from h2.config import H2Configuration
from h2.connection import H2Connection

from dubbo.loggers import loggerFactory
from dubbo.remoting.aio import ConnectionStateListener, EmptyConnectionStateListener
from dubbo.remoting.aio import constants as h2_constants
from dubbo.remoting.aio.exceptions import ProtocolError
from dubbo.remoting.aio.http2.controllers import RemoteFlowController
from dubbo.remoting.aio.http2.frames import (
    DataFrame,
    HeadersFrame,
    Http2Frame,
    PingFrame,
    RstStreamFrame,
    UserActionFrames,
    WindowUpdateFrame,
)
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import Http2Stream
from dubbo.remoting.aio.http2.utils import Http2EventUtils
from dubbo.url import URL
from dubbo.utils import EventHelper, FutureHelper

__all__ = ["AbstractHttp2Protocol", "Http2ClientProtocol", "Http2ServerProtocol"]

_LOGGER = loggerFactory.get_logger()


class AbstractHttp2Protocol(asyncio.Protocol, abc.ABC):
    """
    HTTP/2 protocol implementation.
    """

    DEFAULT_PING_DATA = struct.pack(">Q", 0)  # 8 bytes of 0

    __slots__ = [
        "_url",
        "_loop",
        "_h2_connection",
        "_transport",
        "_flow_controller",
        "_stream_handler",
        "_last_read",
        "_last_write",
    ]

    def __init__(self, url: URL, h2_config: H2Configuration):
        self._url = url
        self._loop = asyncio.get_running_loop()

        # Create the H2 state machine
        self._h2_connection = H2Connection(h2_config)

        # The transport instance
        self._transport: Optional[asyncio.Transport] = None

        self._flow_controller: Optional[RemoteFlowController] = None

        self._stream_handler = self._url.attributes[h2_constants.STREAM_HANDLER_KEY]

        # last time of receiving data
        self._last_read = time.time()
        # last time of sending data
        self._last_write = time.time()

    @property
    def last_read(self) -> float:
        """
        Get the last time of receiving data.
        """
        return self._last_read

    def _update_last_read(self) -> None:
        """
        Update the last time of receiving data.
        """
        self._last_read = time.time()

    @property
    def last_write(self) -> float:
        """
        Get the last time of sending data.
        """
        return self._last_write

    def _update_last_write(self) -> None:
        """
        Update the last time of sending data.
        """
        self._last_write = time.time()

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
            self._send_headers_frame(frame, stream, event)
        elif frame_type == Http2FrameType.DATA:
            self._flow_controller.write_data(stream, frame, event)
        elif frame_type == Http2FrameType.RST_STREAM:
            self._send_reset_frame(frame.stream_id, frame.error_code.value, event)
        else:
            _LOGGER.warning(f"Unhandled frame: {frame}")

    def _send_headers_frame(
        self,
        frame: HeadersFrame,
        stream: Http2Stream,
        event: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Send the HTTP/2 headers frame.(thread-unsafe)
         :param frame: The frame to send.
        :type frame: HeadersFrame
        :param stream: The stream.
        :type stream: Http2Stream
        :param event: The event to be set after sending the frame.
        """
        if stream.id == -1:
            stream.id = self._h2_connection.get_next_available_stream_id()
            self._stream_handler.put_stream(stream.id, stream)

        self._h2_connection.send_headers(
            stream.id, frame.headers.to_list(), end_stream=frame.end_stream
        )
        self._flush()
        EventHelper.set(event)

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

    def _send_ping_frame(self, data: bytes = DEFAULT_PING_DATA) -> None:
        """
        Send the HTTP/2 ping frame.(thread-unsafe)
        :param data: The data to send. The length of the data must be 8 bytes.
        :type data: bytes
        """
        self._h2_connection.ping(data)
        self._flush()

    def _flush(self) -> None:
        """
        Flush the data to the transport.
        """
        outbound_data = self._h2_connection.data_to_send()
        if outbound_data != b"":
            self._transport.write(outbound_data)
            # Update the last write time
            self._update_last_write()

    def data_received(self, data):
        """
        Called when some data is received from the transport.
        :param data: The data received.
        :type data: bytes
        """
        # Update the last read time
        self._update_last_read()

        # Process the event
        events = self._h2_connection.receive_data(data)
        try:
            for event in events:
                frame = Http2EventUtils.convert_to_frame(event)

                # If frame is None, there are two possible cases:
                # 1. Events that are handled automatically by the H2 library (e.g. RemoteSettingsChanged, PingReceived).
                #    -> We just need to send it.
                # 2. Events that are not implemented or do not require attention. -> We'll ignore it for now.
                if frame is not None:
                    if isinstance(frame, WindowUpdateFrame):
                        # Because flow control may be at the connection level, it is handled here
                        self._flow_controller.release_flow_control(frame)
                    elif isinstance(frame, (HeadersFrame, DataFrame, RstStreamFrame)):
                        # Handle the frame by the stream handler
                        self._stream_handler.handle_frame(frame)
                    else:
                        # Try handling other frames
                        self._do_other_frame(frame)

                # Flush the data
                self._flush()

        except Exception as e:
            raise ProtocolError("Failed to process the Http/2 event.") from e

    def _do_other_frame(self, frame: Http2Frame):
        """
        This is a scalable approach to handle other frames. Subclasses can override this method to handle other frames.
        :param frame: The frame to handle.
        :type frame: Http2Frame
        """
        pass

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


class Http2ClientProtocol(AbstractHttp2Protocol):
    """
    HTTP/2 client protocol implementation.
    """

    def __init__(
        self,
        url: URL,
        connection_listener: ConnectionStateListener = None,
    ):
        super().__init__(
            url, H2Configuration(client_side=True, header_encoding="utf-8")
        )
        self._connection_listener = (
            connection_listener or EmptyConnectionStateListener()
        )

        # get heartbeat interval -> default 60s
        self._heartbeat_interval = url.parameters.get(
            h2_constants.HEARTBEAT_KEY, h2_constants.DEFAULT_HEARTBEAT
        )
        self._ping_ack_future: Optional[asyncio.Future] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    def connection_made(self, transport: asyncio.Transport):
        super().connection_made(transport)

        # Start the heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Notify the connection is established
        asyncio.create_task(self._connection_listener.connection_made())

    def _do_other_frame(self, frame: Http2Frame):
        # Handle the ping frame
        if isinstance(frame, PingFrame) and frame.ack:
            FutureHelper.set_result(self._ping_ack_future, None)

    async def _heartbeat_loop(self):
        """
        Heartbeat loop. It is used to check the connection status.
        """
        while True:
            await asyncio.sleep(self._heartbeat_interval)

            # check last read time
            now = time.time()
            if now - self.last_read < self._heartbeat_interval:
                # the connection is normal
                continue

            # try to send ping frame to check the connection
            self._ping_ack_future = asyncio.Future()
            self._send_ping_frame()
            try:
                # wait for the ping ack
                await asyncio.wait_for(self._ping_ack_future, timeout=5)
            except asyncio.TimeoutError:
                # close the connection
                self.close()
                break

    def connection_lost(self, exc):
        super().connection_lost(exc)

        # Notify the connection is lost
        asyncio.create_task(self._connection_listener.connection_lost(exc))


class Http2ServerProtocol(AbstractHttp2Protocol):
    """
    HTTP/2 server protocol implementation.
    """

    def __init__(self, url: URL):
        super().__init__(
            url, H2Configuration(client_side=False, header_encoding="utf-8")
        )
