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

from dubbo.logger.logger_factory import loggerFactory
from dubbo.protocol.triple.stream import ClientStream, ServerStream, Stream
from dubbo.remoting.aio.constants import END_DATA_SENTINEL

logger = loggerFactory.get_logger(__name__)

HEADER_FRAME = "HEADER_FRAME"
DATA_FRAME = "DATA_FRAME"
TRAILER_FRAME = "TRAILER_FRAME"


class AioStream(Stream):
    """
    The Stream object for HTTP/2
    """

    def __init__(self, stream_id: int, loop, protocol):
        super().__init__(stream_id)
        # The loop to run the asynchronous function.
        self._loop = loop
        # The protocol to send the frame.
        self._protocol = protocol

        # The flag to indicate whether the header has been sent.
        self._header_emitted = False
        # This is an event that send a header frame.
        # It is used to ensure that the header frame is sent before the data frame.
        self._send_header_event: Optional[asyncio.Event] = None

        # The queue to store the all frames to send. It is used to ensure the order of the frames.
        self._write_queue = asyncio.Queue()
        # This is an event that send a data frame.
        # It is used to ensure that the data frame is sent before the next data frame.
        self._send_data_event: Optional[asyncio.Event] = None

        # The task to send the frames.
        self._send_loop_task = self._loop.create_task(self._send_loop())

        # The flag to indicate whether the sending is completed.
        # However, it does not mean that all the data has been sent successfully,
        # but is only used to prevent other data from being sent.
        self._send_completed = False

        # The flag to indicate whether the receiving is completed.
        self._receive_completed = False

    def send_headers(self, headers: List[Tuple[str, str]]) -> None:
        """
        The first call sends the head frame, the second call sends the trailer frame.
        Args:
            headers: The headers to send.
        """
        if self._send_completed:
            raise RuntimeError("The stream has finished sending data")

        if self._header_emitted:
            # If the header has been sent, it means that the trailer is being sent.
            self._send_completed = True
        else:
            self._header_emitted = True

        def _inner_send_headers(headers, end_stream):
            data_type = TRAILER_FRAME if end_stream else HEADER_FRAME
            self._write_queue.put_nowait((data_type, headers))

        self._loop.call_soon_threadsafe(
            _inner_send_headers, headers, self._send_completed
        )

    def send_data(self, data: bytes) -> None:
        """
        Send the data frame.
        Args:
            data: The data to send.
        """
        if self._send_completed:
            raise RuntimeError("The stream has finished sending data")
        elif not self._header_emitted:
            raise RuntimeError("The header has not been sent")

        def _inner_send_data(data):
            self._write_queue.put_nowait((DATA_FRAME, data))

        self._loop.call_soon_threadsafe(_inner_send_data, data)

    def send_end_stream(self) -> None:
        """
        Send the end stream frame -> An empty data frame will be sent (end_stream=True)
        """

        def _inner_send_end_stream():
            self._write_queue.put_nowait((DATA_FRAME, END_DATA_SENTINEL))

        self._loop.call_soon_threadsafe(_inner_send_end_stream)

    async def _send_loop(self):
        """
        Asynchronous blocking to get data from write_queue and send it.
        The purpose of using write_queue is to ensure that frames are sent in the following order:
        1. HEADER_FRAME
        2. DATA_FRAME  (0 or more)
        3. TRAILER_FRAME (optional)
        The format of the queue elements is: (type, data) -> (HEADER_FRAME, [("key", "value")]) or (DATA_FRAME, b"")
        """
        while True:
            data_type, data = await self._write_queue.get()

            if data_type == HEADER_FRAME:
                # If the data is a header frame, send it directly.
                self._send_header_event = self._protocol.send_head_frame(
                    self._stream_id, data
                )
                continue

            # Waiting for the headers to be sent
            assert self._send_header_event is not None
            await self._send_header_event.wait()

            if self._send_data_event:
                # Waiting for the previous message to be sent
                await self._send_data_event.wait()

            if data_type == DATA_FRAME and data:
                self._send_data_event = self._protocol.send_data_frame(
                    self._stream_id, data
                )
                if data == END_DATA_SENTINEL:
                    # If it is an END_DATA_SENTINEL, it means that the data has been sent.
                    break
            elif data_type == TRAILER_FRAME:
                # If it is a TRAILER_FRAME, then it must also be a last frame,
                # so it exits the loop when it finishes sending.
                self._protocol.send_head_frame(self._stream_id, data, end_stream=True)
                break


class AioClientStream(AioStream, ClientStream):
    """
    The Stream object for the HTTP/2. (client side)
    """

    def __init__(self, loop, protocol, listener: ClientStream.Listener):
        super().__init__(protocol.conn.get_next_available_stream_id(), loop, protocol)
        self._protocol.register_stream(self._stream_id, self)

        # receive data
        self._listener = listener

    def receive_headers(self, headers: List[Tuple[str, str]]) -> None:
        """
        Receive the headers.
        """
        # Running synchronized functions non-blocking
        self._loop.run_in_executor(None, self._listener.on_headers, headers)

    def receive_data(self, data: bytes) -> None:
        """
        Receive the data.
        """
        self._loop.run_in_executor(None, self._listener.on_data, data)

    def receive_trailers(self, trailers: List[Tuple[str, str]]) -> None:
        """
        Receive the trailers.
        """
        self._loop.run_in_executor(None, self._listener.on_trailers, trailers)

    def receive_complete(self):
        self._receive_completed = True


class AioServerStream(AioStream, ServerStream):
    """
    The Stream object for the HTTP/2. (server side)
    """

    def __init__(self, stream_id, loop, protocol):
        super().__init__(stream_id, loop, protocol)

    def receive_headers(self, headers: List[Tuple[str, str]]) -> None:
        pass

    def receive_data(self, data: bytes) -> None:
        pass

    def receive_trailers(self, trailers: List[Tuple[str, str]]) -> None:
        pass

    def receive_complete(self):
        self._receive_completed = True
