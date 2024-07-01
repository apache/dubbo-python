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

import h2.events
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived,
    PingReceived,
    RemoteSettingsChanged,
    RequestReceived,
    ResponseReceived,
    StreamEnded,
    StreamReset,
    TrailersReceived,
    WindowUpdated,
)

from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.constants import END_DATA_SENTINEL

logger = loggerFactory.get_logger(__name__)


class HTTP2Protocol(asyncio.Protocol):

    def __init__(self, h2_config: H2Configuration):
        # Create the H2 state machine
        self.conn: H2Connection = H2Connection(config=h2_config)

        # the backing transport.
        self.transport: Optional[asyncio.Transport] = None

        # The asyncio event loop.
        self._loop = asyncio.get_running_loop()

        # A mapping of stream ID to stream object.
        self.streams = {}

        # The `write_data_queue`, `flow_controlled_data`, and `send_data_loop_task` together form the flow control mechanism.
        # Data flows between `write_queue` and `flow_controlled_data`.
        # The `send_data_loop_task` blocks while reading data from the `write_queue` and attempts to send it.
        # If a flow control limit is encountered, the unsent data is stored in `flow_controlled_data`,
        # awaiting a WINDOW_UPDATE frame, at which point it is moved back from `flow_controlled_data` to `write_queue`.
        self._write_data_queue = asyncio.Queue()
        self._flow_controlled_data = {}
        self._send_data_loop_task = None

        # Any streams that have been remotely reset.
        self._reset_streams = set()

    def connection_made(self, transport: asyncio.Transport) -> None:
        """
        Called when the connection is first established. We complete the following actions:
        1. Save the transport.
        2. Initialize the H2 connection.
        3. Create the send data loop task.
        """
        self.transport = transport
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())
        self._send_data_loop_task = self._loop.create_task(self._send_data_loop())

    def connection_lost(self, exc) -> None:
        """
        Called when the connection is lost.
        """
        self._send_data_loop_task.cancel()

    def send_head_frame(
        self,
        stream_id: int,
        headers: List[Tuple[str, str]],
        end_stream=False,
        head_event: Optional[asyncio.Event] = None,
    ) -> asyncio.Event:
        """
        Send headers to the remote peer.
        Because flow control is only for data frames, we can directly send the head frame rate.
        Note: Only the first call sends a head frame, if called again, a trailer frame is sent.
        """
        head_event = head_event or asyncio.Event()

        def _inner_send_header_frame(stream_id, headers, event):
            self.conn.send_headers(stream_id, headers, end_stream)
            self.transport.write(self.conn.data_to_send())
            event.set()

        # Send the header frame
        self._loop.call_soon_threadsafe(
            _inner_send_header_frame, stream_id, headers, head_event
        )

        return head_event

    def send_data_frame(self, stream_id: int, data) -> asyncio.Event:
        """
        Send data to the remote peer.
        The sending of data frames is subject to traffic control,
        so we put them in a queue and send them according to traffic control rules
        Args:
            stream_id: stream id
            data: data
        """
        event = asyncio.Event()

        def _inner_send_data_frame(stream_id: int, data, event: asyncio.Event):
            self._write_data_queue.put_nowait((stream_id, data, event))

        self._loop.call_soon_threadsafe(_inner_send_data_frame, stream_id, data, event)

        return event

    async def _send_data_loop(self) -> None:
        """
        Asynchronous blocking to get data from write_data_queue and try to send it,
        this method implements the flow control mechanism
        """
        while True:
            stream_id, data, event = await self._write_data_queue.get()

            # If this stream got reset, just drop the data on the floor.
            if stream_id in self._reset_streams:
                event.set()
                continue

            if data is END_DATA_SENTINEL:
                self.conn.end_stream(stream_id)
                self.transport.write(self.conn.data_to_send())
                event.set()
                continue

            # We need to send data, but not to exceed the flow control window.
            window_size = self.conn.local_flow_control_window(stream_id)
            chunk_size = min(window_size, len(data))
            data_to_send = data[:chunk_size]
            data_to_buffer = data[chunk_size:]

            if data_to_send:
                # Send the data frame
                max_size = self.conn.max_outbound_frame_size
                chunks = (
                    data_to_send[x : x + max_size]
                    for x in range(0, len(data_to_send), max_size)
                )
                for chunk in chunks:
                    self.conn.send_data(stream_id, chunk)
                self.transport.write(self.conn.data_to_send())

            if data_to_buffer:
                # We still have data to send, but it's blocked by traffic control,
                # so we need to wait for the traffic window to open again.
                self._flow_controlled_data[stream_id] = (
                    stream_id,
                    data_to_buffer,
                    event,
                )
            else:
                # We sent everything.
                event.set()

    def data_received(self, data: bytes) -> None:
        """
        Process inbound data.
        """
        events = self.conn.receive_data(data)
        for event in events:
            self._process_event(event)
            outbound_data = self.conn.data_to_send()
            if outbound_data:
                self.transport.write(outbound_data)

    def _process_event(self, event: h2.events.Event) -> Optional[bool]:
        """
        Process an event.
        """
        if isinstance(event, (RemoteSettingsChanged, PingReceived)):
            # Events that are handled automatically by the H2 library.
            # 1. RemoteSettingsChanged: h2 automatically acknowledges settings changes
            # 2. PingReceived: A ping acknowledgment with the same opaque data is automatically emitted after receiving a ping.
            pass
        elif isinstance(event, WindowUpdated):
            self.window_updated(event)
        elif isinstance(event, StreamReset):
            self.reset_stream(event)
        else:
            # A False here means that the current event is not handled and needs to be handled by the subclass.
            return False

    def window_updated(self, event: WindowUpdated) -> None:
        """
        The flow control window got opened.

        """
        if event.stream_id:
            # This is specific to a single stream.
            if event.stream_id in self._flow_controlled_data:
                self._write_data_queue.put_nowait(
                    self._flow_controlled_data.pop(event.stream_id)
                )
        else:
            # This event is specific to the connection.
            # Free up all the streams.
            for data in self._flow_controlled_data.values():
                self._write_data_queue.put_nowait(data)

            self._flow_controlled_data = {}

    def reset_stream(self, event: StreamReset) -> None:
        """
        The remote peer reset the stream.
        """
        if event.stream_id in self._flow_controlled_data:
            del self._flow_controlled_data

        self._reset_streams.add(event.stream_id)


class HTTP2ClientProtocol(HTTP2Protocol):
    """
    An HTTP/2 client protocol.
    """

    def __init__(self):
        h2_config = H2Configuration(client_side=True, header_encoding="utf-8")
        super().__init__(h2_config)

    def register_stream(self, stream_id, stream):
        self.streams[stream_id] = stream

    def _process_event(self, event):
        if super()._process_event(event) is False:
            if isinstance(event, ResponseReceived):
                self.receive_headers(event)
            elif isinstance(event, DataReceived):
                self.receive_data(event)
            elif isinstance(event, TrailersReceived):
                self.receive_trailers(event)
            elif isinstance(event, StreamEnded):
                self.stream_ended(event)

    def receive_headers(self, event: ResponseReceived):
        """
        The response headers have been received.
        """
        self.streams[event.stream_id].receive_headers(event.headers)

    def receive_data(self, event: DataReceived):
        """
        Data has been received.
        """
        self.streams[event.stream_id].receive_data(event.data)
        # Acknowledge the data, so the remote peer can send more.
        self.conn.acknowledge_received_data(
            event.flow_controlled_length, event.stream_id
        )

    def receive_trailers(self, event):
        """
        Trailers have been received.
        """
        self.streams[event.stream_id].receive_trailers(event.headers)

    def stream_ended(self, event):
        """
        The stream has ended.
        """
        self.streams[event.stream_id].receive_complete()
        # Clean up the stream.
        del self.streams[event.stream_id]

    def reset_stream(self, event: StreamReset) -> None:
        super().reset_stream(event)
        # TODO Pass the exception to the corresponding stream object


class HTTP2ServerProtocol(HTTP2Protocol):

    def __init__(self):
        h2_config = H2Configuration(client_side=False, header_encoding="utf-8")
        super().__init__(h2_config)

    def _process_event(self, event: h2.events.Event):
        if super()._process_event(event) is False:
            if isinstance(event, RequestReceived):
                self.receive_headers(event)
            elif isinstance(event, DataReceived):
                self.receive_data(event)
            elif isinstance(event, StreamEnded):
                self.stream_ended(event)

    def receive_headers(self, event: RequestReceived):
        """
        The request headers have been received.
        """
        from dubbo.remoting.aio.aio_stream import AioServerStream

        s = AioServerStream(event.stream_id, self._loop, self)
        self.streams[event.stream_id] = s
        s.receive_headers(event.headers)

    def receive_data(self, event: DataReceived):
        """
        Data has been received.
        """
        self.streams[event.stream_id].receive_data(event.data)

    def stream_ended(self, event: StreamEnded):
        """
        The stream has ended.
        """
        self.streams[event.stream_id].receive_complete()
