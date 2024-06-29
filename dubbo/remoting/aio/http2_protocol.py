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
from h2.events import (DataReceived, RemoteSettingsChanged, RequestReceived,
                       ResponseReceived, StreamEnded, TrailersReceived,
                       WindowUpdated)
from h2.exceptions import ProtocolError, StreamClosedError
from h2.settings import SettingCodes

from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


class Http2Protocol(asyncio.Protocol):

    def __init__(self, h2_config: H2Configuration):
        h2_config.logger = logger
        self.conn = H2Connection(config=h2_config)
        self.transport = None
        self.flow_control_futures = {}

    def connection_made(self, transport: asyncio.Transport) -> None:
        self.transport = transport
        self.conn.initiate_connection()

    def connection_lost(self, exc: Exception) -> None:
        if exc:
            logger.error(f"Connection lost: {exc}")
        else:
            logger.info("Connection closed cleanly.")
            self.transport.close()

    async def send_headers(
        self,
        headers: List[Tuple[str, str]],
        stream_id: Optional[int] = None,
        end_stream=False,
    ) -> int:
        """
        Send headers to the server or client.
        Args:
            headers: A list of header tuples.
            stream_id: The stream ID to send the headers on. If None, a new stream will be created.
            end_stream: Whether to close the stream after sending the headers.
        Returns:
            The stream ID the headers were sent on.
        """
        if not stream_id:
            # Get the next available stream ID.
            stream_id = self.conn.get_next_available_stream_id()
        self.conn.send_headers(stream_id, headers, end_stream=end_stream)
        self.transport.write(self.conn.data_to_send())
        return stream_id

    async def send_data(self, stream_id: int, data: bytes, end_stream=False) -> None:
        """
         Send data according to the flow control rules.
        Args:
            stream_id: The stream ID to send the data on.
            data: The data to send.
            end_stream: Whether to close the stream after sending the data.
        """
        while data:
            # Check the flow control window.
            while self.conn.local_flow_control_window(stream_id) < 1:
                try:
                    # Wait for flow control window to open.
                    await self.wait_for_flow_control(stream_id)
                except asyncio.CancelledError:
                    return
            # Determine how much data to send.
            chunk_size = min(
                self.conn.local_flow_control_window(stream_id),
                len(data),
                self.conn.max_outbound_frame_size,
            )
            try:
                # Send the data.
                self.conn.send_data(
                    stream_id,
                    data[:chunk_size],
                    end_stream=(chunk_size == len(data) and end_stream),
                )
            except (StreamClosedError, ProtocolError):
                logger.error(
                    f"Stream {stream_id} closed unexpectedly, aborting data send."
                )
                break

            self.transport.write(self.conn.data_to_send())
            data = data[chunk_size:]

    def data_received(self, data: bytes) -> None:
        try:
            # Parse the received data.
            events = self.conn.receive_data(data)

            if not events:
                self.transport.write(self.conn.data_to_send())
            else:
                # Process the events.
                for event in events:
                    if isinstance(event, ResponseReceived) or isinstance(
                        event, RequestReceived
                    ):
                        self.receive_headers(event.stream_id, event.headers)
                    elif isinstance(event, DataReceived):
                        self.receive_data(event.stream_id, event.data)
                    elif isinstance(event, TrailersReceived):
                        self.receive_trailers(event.stream_id, event.headers)
                    elif isinstance(event, StreamEnded):
                        self.receive_end(event.stream_id)
                    elif isinstance(event, WindowUpdated):
                        self.window_updated(event.stream_id, event.delta)
                    elif isinstance(event, RemoteSettingsChanged):
                        if SettingCodes.INITIAL_WINDOW_SIZE in event.changed_settings:
                            self.window_updated(None, 0)

                data = self.conn.data_to_send()
                if data:
                    self.transport.write(data)

        except ProtocolError:
            logger.exception("Parse HTTP2 frame error")
            self.transport.write(self.conn.data_to_send())
            self.transport.close()

    async def wait_for_flow_control(self, stream_id) -> None:
        """
        Waits for a Future that fires when the flow control window is opened.
        """
        f = asyncio.Future()
        self.flow_control_futures[stream_id] = f
        await f

    def window_updated(self, stream_id, delta) -> None:
        """
        A window update frame was received. Unblock some number of flow control Futures.
        """
        if stream_id and stream_id in self.flow_control_futures:
            future = self.flow_control_futures.pop(stream_id)
            future.set_result(delta)
        else:
            # If it does not match, remove all flow control.
            for f in self.flow_control_futures.values():
                f.set_result(delta)
            self.flow_control_futures.clear()
