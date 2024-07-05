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
from typing import Dict, Optional, Tuple

from h2.config import H2Configuration
from h2.connection import H2Connection

from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.h2_frame import H2Frame, H2FrameType, H2FrameUtils
from dubbo.remoting.aio.h2_stream_handler import StreamHandler

logger = loggerFactory.get_logger(__name__)


class DataFlowControl:
    """
    DataFlowControl is responsible for managing HTTP/2 data flow, handling flow control,
    and ensuring data frames are sent according to the HTTP/2 flow control rules.

    Note:
        The class is not thread-safe and does not need to be designed as thread-safe
        because there can be only one DataFlowControl corresponding to an HTTP2 connection.

    Args:
        protocol (H2Protocol): The protocol instance used to send frames.
        loop (asyncio.AbstractEventLoop): The asyncio event loop.
    """

    def __init__(self, protocol, loop: asyncio.AbstractEventLoop):
        # The protocol instance used to send frames.
        self.protocol: H2Protocol = protocol

        # The asyncio event loop.
        self.loop = loop

        # Queue for storing data to be sent out
        self._outbound_data_queue: asyncio.Queue[Tuple[H2Frame, asyncio.Event]] = (
            asyncio.Queue()
        )

        # Dictionary for storing data that could not be sent due to flow control limits
        self._flow_control_data: Dict[int, Tuple[H2Frame, asyncio.Event]] = {}

        # Set of streams that need to be reset
        self._reset_streams = set()

        # Task for the data sender loop.
        self._data_sender_loop_task = None

    def start(self) -> None:
        """
        Start the data sender loop.
        This creates and starts an asyncio task that runs the _data_sender_loop coroutine.
        """
        # Start the data sender loop
        self._data_sender_loop_task = self.loop.create_task(self._data_sender_loop())

    def cancel(self) -> None:
        """
        Cancel the data sender loop.
        This cancels the asyncio task running the _data_sender_loop coroutine.
        """
        if self._data_sender_loop_task:
            self._data_sender_loop_task.cancel()

    def put(self, frame: H2Frame, event: asyncio.Event) -> None:
        """
        Put a data frame into the outbound data queue.

        Args:
            frame (H2Frame): The data frame to send.
            event (asyncio.Event): The event to notify when the data frame is sent.
        """
        self._outbound_data_queue.put_nowait((frame, event))

    def release(self, frame: H2Frame) -> None:
        """
        Release the flow control for the stream.

        Args:
            frame (H2Frame): The data frame to release the flow control.
                             It must be a WINDOW_UPDATE frame.
        """
        if frame.frame_type != H2FrameType.WINDOW_UPDATE:
            raise TypeError("The frame is not a window update frame")

        stream_id = frame.stream_id
        if stream_id:
            # This is specific to a single stream.
            if stream_id in self._flow_control_data:
                data_frame_event = self._flow_control_data.pop(stream_id)
                self._outbound_data_queue.put_nowait(data_frame_event)
        else:
            # This is for the entire connection.
            for data_frame_event in self._flow_control_data.values():
                self._outbound_data_queue.put_nowait(data_frame_event)
            # Clear the pending data
            self._flow_control_data = {}

    def reset(self, frame: H2Frame) -> None:
        """
        Reset the stream.

        Args:
            frame (H2Frame): The reset frame. It must be an RST_STREAM frame.
        """
        if frame.frame_type != H2FrameType.RST_STREAM:
            raise TypeError("The frame is not a reset stream frame")

        if frame.stream_id in self._flow_control_data:
            del self._flow_control_data[frame.stream_id]

        self._reset_streams.add(frame.stream_id)

    async def _data_sender_loop(self) -> None:
        """
        Coroutine that continuously sends data frames from the outbound data queue
        while respecting flow control limits.
        """
        while True:
            # Get the frame from the outbound data queue -> it's a blocking operation, but asynchronous.
            data_frame: H2Frame
            event: asyncio.Event
            data_frame, event = await self._outbound_data_queue.get()

            # If the frame is not a data frame, ignore it.
            if data_frame.frame_type != H2FrameType.DATA:
                logger.warning(f"Invalid frame type: {data_frame.frame_type}, ignored")
                event.set()
                continue

            # Get the stream ID and data from the frame.
            stream_id = data_frame.stream_id
            data = data_frame.data
            end_stream = data_frame.end_stream

            # The stream has been reset, so we don't send any data.
            if stream_id in self._reset_streams:
                event.set()
                continue

            # We need to send data, but not to exceed the flow control window.
            window_size = self.protocol.conn.local_flow_control_window(stream_id)
            chunk_size = min(window_size, len(data))
            data_to_send = data[:chunk_size]
            data_to_buffer = data[chunk_size:]

            if data_to_send:
                # Send the data frame
                max_size = self.protocol.conn.max_outbound_frame_size

                # Split the data into chunks and send them out
                for x in range(0, len(data), max_size):
                    chunk = data[x : x + max_size]
                    end_stream_flag = (
                        end_stream
                        and data_to_buffer == b""
                        and x + max_size >= len(data)
                    )
                    self.protocol.conn.send_data(
                        stream_id, chunk, end_stream=end_stream_flag
                    )

                self.protocol.transport.write(self.protocol.conn.data_to_send())
            elif end_stream:
                # If there is no data to send, but the stream is ended, send an empty data frame.
                self.protocol.conn.send_data(stream_id, b"", end_stream=True)
                self.protocol.transport.write(self.protocol.conn.data_to_send())

            if data_to_buffer:
                # Store the data that could not be sent due to flow control limits
                data_frame.data = data_to_buffer
                self._flow_control_data[stream_id] = (data_frame, event)
            else:
                # We sent everything.
                event.set()


class H2Protocol(asyncio.Protocol):
    """
    Implements an HTTP/2 protocol using asyncio's Protocol class.

    This class sets up and manages an HTTP/2 connection using the h2 library.
    It handles connection state, stream mapping, and data flow control.

    Args:
        h2_config (H2Configuration): The configuration for the H2 connection.
        stream_handler (StreamHandler): The handler for managing streams.

    """

    def __init__(self, h2_config: H2Configuration, stream_handler: StreamHandler):
        # Create the H2 state machine
        self.conn: H2Connection = H2Connection(config=h2_config)

        # the backing transport.
        self.transport: Optional[asyncio.Transport] = None

        # The asyncio event loop.
        self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        # A mapping of stream ID to stream object.
        self._stream_handler: StreamHandler = stream_handler

        self._data_follow_control: Optional[DataFlowControl] = None

    def connection_made(self, transport: asyncio.Transport) -> None:
        """
        Called when the connection is first established. We complete the following actions:
        1. Save the transport.
        2. Initialize the H2 connection.
        3. Initialize the StreamHandler.
        3. Create the data follow control and start the task.
        """
        self.transport = transport
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

        # Initialize the StreamHandler
        self._stream_handler.init(self.loop, self)

        # Create the data follow control object and start the task.
        self._data_follow_control = DataFlowControl(self, self.loop)
        self._data_follow_control.start()

    def connection_lost(self, exc) -> None:
        """
        Called when the connection is lost.
        Args:
            exc: The exception that caused the connection to be lost.
        """
        self._stream_handler.destroy()
        self._data_follow_control.cancel()

    def send_headers_frame(self, headers_frame: H2Frame) -> asyncio.Event:
        """
        Send headers to the remote peer. (thread-safe)
        Note:
            Only the first call sends a head frame, if called again, a trailer frame is sent.
        Args:
            headers_frame(H2Frame): The headers frame to send.
        Returns:
            asyncio.Event: The event that is set when the headers frame is sent.
        """
        headers_event = asyncio.Event()

        def _inner_send_headers_frame(headers_frame: H2Frame, event: asyncio.Event):
            self.conn.send_headers(
                headers_frame.stream_id, headers_frame.data, headers_frame.end_stream
            )
            self.transport.write(self.conn.data_to_send())
            # Set the event to indicate that the headers frame has been sent.
            event.set()

        # Send the header frame
        self.loop.call_soon_threadsafe(
            _inner_send_headers_frame, headers_frame, headers_event
        )

        return headers_event

    def send_data_frame(self, data_frame: H2Frame) -> asyncio.Event:
        """
        Send data to the remote peer. (thread-safe)
        The sending of data frames is subject to traffic control.
        Args:
            data_frame(H2Frame): The data frame to send.
        Returns:
            asyncio.Event: The event that is set when the data frame is sent.
        """
        data_event = asyncio.Event()

        def _inner_send_data_frame(_data_frame: H2Frame, event: asyncio.Event):
            self._data_follow_control.put(_data_frame, event)

        self.loop.call_soon_threadsafe(_inner_send_data_frame, data_frame, data_event)

        return data_event

    def send_reset_frame(self, reset_frame: H2Frame) -> None:
        """
        Send the reset frame to the remote peer.(thread-safe)
        Args:
            reset_frame(H2Frame): The reset frame to send.
        """

        def _inner_send_reset_frame(_reset_frame: H2Frame):
            self.conn.reset_stream(_reset_frame.stream_id, _reset_frame.data)
            self.transport.write(self.conn.data_to_send())
            # remove the stream from the stream handler
            self._stream_handler.remove(_reset_frame.stream_id)

        self.loop.call_soon_threadsafe(_inner_send_reset_frame, reset_frame)

    def data_received(self, data: bytes) -> None:
        """
        Process inbound data.
        """
        events = self.conn.receive_data(data)
        # Process the event
        for event in events:
            frame = H2FrameUtils.create_frame_by_event(event)
            if not frame:
                # If frame is None, there are two possible cases:
                # 1. Events that are handled automatically by the H2 library. -> We just need to send it.
                #    e.g. RemoteSettingsChanged, PingReceived
                # 2. Events that are not implemented or do not require attention. -> We'll ignore it for now.
                pass
            else:
                # The frames we focus on include: HEADERS, DATA, WINDOW_UPDATE, RST_STREAM
                if frame.frame_type == H2FrameType.WINDOW_UPDATE:
                    # Update the flow control window
                    self._data_follow_control.release(frame)
                else:
                    # Handle the frame
                    self._stream_handler.handle_frame(frame)

                # Acknowledge the received data
                if frame.frame_type == H2FrameType.DATA:
                    self.conn.acknowledge_received_data(
                        frame.attributes["flow_controlled_length"], frame.stream_id
                    )

            # If there is data to send, send it.
            outbound_data = self.conn.data_to_send()
            if outbound_data:
                self.transport.write(outbound_data)
