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
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Union

from h2.connection import H2Connection

from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.http2.frames import DataFrame, HeadersFrame, Http2Frame
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import Http2Stream

logger = loggerFactory.get_logger(__name__)


class FollowController:
    """
    HTTP/2 stream flow controller.
    Note:
        This is a thread-unsafe class and must be used in the Http2Protocol class

    Args:
        loop: The asyncio event loop.
        h2_connection: The H2 connection.
        transport: The asyncio transport.
    """

    @dataclass
    class StreamItem:
        """
        The item for storing stream, flag, and event.
        Args:
            stream: The stream.
            half_close: Whether to close the stream after sending the data.
            event: This event is triggered when all data has been sent.
        """

        stream: Http2Stream
        half_close: bool
        event: asyncio.Event

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        h2_connection: H2Connection,
        transport: asyncio.Transport,
    ):
        self._loop = loop
        self._h2_connection = h2_connection
        self._transport = transport

        # Collection of all streams that need to send data
        self._stream_dict: Dict[int, FollowController.StreamItem] = {}

        # Collection of streams that are currently sending data
        self._outbound_stream_queue: asyncio.Queue[FollowController.StreamItem] = (
            asyncio.Queue()
        )

        # Collection of streams that are flow-controlled
        self._follow_control_dict: Dict[int, FollowController.StreamItem] = {}

        # Actual storage for the data that needs to be sent
        self._data_dict: Dict[int, bytearray] = {}

        # The task for sending data.
        self._task = None

    def start(self) -> None:
        """
        Start the data sender loop.
        This creates and starts an asyncio task that runs the _data_sender_loop coroutine.
        """
        self._task = self._loop.create_task(self._send_data())

    def increment_flow_control_window(self, stream_id: Optional[int]) -> None:
        """
        Increment the flow control window size.
        Args:
            stream_id: The stream identifier. If it is None, it means the entire connection.
        """
        if stream_id is None or stream_id == 0:
            # This is for the entire connection.
            for item in self._follow_control_dict.values():
                self._outbound_stream_queue.put_nowait(item)
            self._follow_control_dict = {}
        elif stream_id in self._follow_control_dict:
            # This is specific to a single stream.
            item = self._follow_control_dict.pop(stream_id)
            self._outbound_stream_queue.put_nowait(item)

    def send_data(
        self,
        stream: Http2Stream,
        data: bytes,
        half_close: bool,
        event: Union[asyncio.Event, threading.Event] = None,
    ):
        """
        Send data to the stream.(thread-unsafe)
        Note:
        Args:
            stream: The stream.
            data: The data to send.
            half_close: Whether to close the stream after sending the data.
            event: The event that is triggered when all data has been sent.
        """

        # Check if the stream is closed
        if stream.is_local_closed():
            if event:
                event.set()
            logger.warning(f"Stream {stream.id} is closed. Ignoring data {data}")
        else:
            # Save the data to the data dictionary
            if old_data := self._data_dict.get(stream.id):
                old_data.extend(data)
                item = self._stream_dict[stream.id]
                item.half_close = half_close
                # Update the event
                if item.event:
                    item.event.set()
                item.event = event
            else:
                self._data_dict[stream.id] = bytearray(data)
                self._stream_dict[stream.id] = FollowController.StreamItem(
                    stream, half_close, event
                )

            # Put the stream into the outbound stream queue
            self._outbound_stream_queue.put_nowait(self._stream_dict[stream.id])

    def stop(self) -> None:
        """
        Stop the data sender loop.
        This cancels the asyncio task that runs the _data_sender_loop coroutine.
        """
        if self._task:
            self._task.cancel()

    async def _send_data(self) -> None:
        """
        Coroutine that continuously sends data frames from the outbound data queue while respecting flow control limits.
        """
        while True:
            # get the data to send.(async blocking)
            item = await self._outbound_stream_queue.get()

            # check if the stream is closed
            stream = item.stream
            if stream.is_local_closed():
                # The local side of the stream is closed, so we don't need to send any data.
                if item.event:
                    item.event.set()
                continue

            # get the flow control window size
            data = self._data_dict.get(stream.id, bytearray())
            window_size = self._h2_connection.local_flow_control_window(stream.id)
            chunk_size = min(window_size, len(data))
            data_to_send = data[:chunk_size]
            data_to_buffer = data[chunk_size:]

            # send the data
            if data_to_send or item.half_close:
                max_size = self._h2_connection.max_outbound_frame_size
                # Split the data into chunks and send them out
                for x in range(0, len(data_to_send), max_size):
                    chunk = data_to_send[x : x + max_size]
                    end_stream_flag = (
                        item.half_close
                        and data_to_buffer == b""
                        and x + max_size >= len(data_to_send)
                    )
                    self._h2_connection.send_data(
                        stream.id, chunk, end_stream=end_stream_flag
                    )

                outbound_data = self._h2_connection.data_to_send()
                if not outbound_data:
                    # If there is no outbound data to send but the stream needs to be closed,
                    # send an empty headers frame with the end_stream flag set to True.
                    self._h2_connection.send_data(stream.id, b"", end_stream=True)
                    outbound_data = self._h2_connection.data_to_send()
                self._transport.write(outbound_data)

            if data_to_buffer:
                # Save the data that could not be sent due to flow control limits
                self._follow_control_dict[stream.id] = item
                self._data_dict[stream.id] = data_to_buffer
            else:
                # If all data has been sent, trigger the event.
                self._data_dict.pop(stream.id)
                if item.event:
                    item.event.set()


class FrameOrderController:
    """
    HTTP/2 frame writer. This class is responsible for writing frames in the correct order.
    Note:
        Some special frames do not need to be sorted through this queue, such as RST_STREAM, WINDOW_UPDATE, etc.
    Args:
        stream: The stream to which the frame belongs.
        loop: The asyncio event loop.
        protocol: The HTTP/2 protocol.
    """

    def __init__(self, stream: Http2Stream, loop: asyncio.AbstractEventLoop, protocol):
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        self._stream: Http2Stream = stream
        self._loop: asyncio.AbstractEventLoop = loop
        self._protocol: Http2Protocol = protocol

        # The queue for writing frames. -> keep the order of frames
        self._frame_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        # The task for writing frames.
        self._send_frame_task: Optional[asyncio.Task] = None

        # some events
        # This event is triggered when a HEADERS frame is placed in the queue.
        self._start_event = asyncio.Event()
        # This event is triggered when the headers are sent.
        self._headers_sent_event: Optional[asyncio.Event] = None
        # This event is triggered when the data is sent.
        self._data_sent_event: Optional[asyncio.Event] = None

        # The trailers frame.
        self._trailers: Optional[HeadersFrame] = None

    def start(self) -> None:
        """
        Start the frame writer loop.
        This creates and starts an asyncio task that runs the _frame_writer_loop coroutine.
        """
        self._send_frame_task = self._loop.create_task(self._write_frame())

    def write_headers(self, frame: HeadersFrame) -> None:
        """
        Write the headers frame to the frame writer queue.(thread-safe)
        Args:
            frame: The headers frame.
        """

        def _inner_operation(_frame: Http2Frame):
            # put the frame into the queue
            self._frame_queue.put_nowait((0, _frame))
            # trigger the start event
            self._start_event.set()

        self._loop.call_soon_threadsafe(_inner_operation, frame)

    def write_data(self, frame: DataFrame, last: bool = False) -> None:
        """
        Write the data frame to the frame writer queue.(thread-safe)
        Args:
            frame: The data frame.
            last: Unlike end_stream, this flag indicates whether the current frame is the last data frame or not.
        """

        def _inner_operation(_frame: Http2Frame, _last: bool):
            # put the frame into the queue
            self._frame_queue.put_nowait((1, _frame))
            if _last:
                # put the trailers frame into the queue
                if self._trailers:
                    self._frame_queue.put_nowait((2, self._trailers))

        self._loop.call_soon_threadsafe(_inner_operation, frame, last)

    def write_trailers(self, frame: HeadersFrame) -> None:
        """
        Write the trailers frame to the frame writer queue.(thread-safe)
        Note:
            This method is suitable for cases where data frames are not to be sent
        Args:
            frame: The trailers frame.
        """

        def _inner_operation(_frame: Http2Frame):
            # put the frame into the queue
            self._frame_queue.put_nowait((2, _frame))

        self._loop.call_soon_threadsafe(_inner_operation, frame)

    def write_trailers_after_data(self, frame: HeadersFrame) -> None:
        """
        Write the trailers frame to the frame writer queue.(thread-safe)
        Note:
            This method is used to write trailers after the data frame.
            If the data frame is not sent completely, the trailers frame will not be sent.
        """
        self._trailers = frame

    async def _write_frame(self) -> None:
        """
        Coroutine that continuously writes frames from the frame queue.
        """
        while True:
            # wait for the start event
            await self._start_event.wait()

            # get the frame from the queue -> block & async
            _, frame = await self._frame_queue.get()

            # write the frame
            if frame.frame_type == Http2FrameType.HEADERS:
                self._headers_sent_event = self._protocol.write(frame, self._stream)
            else:
                # await the headers sent event
                await self._headers_sent_event.wait()

                # await the data sent event
                if self._data_sent_event:
                    await self._data_sent_event.wait()

                self._data_sent_event = self._protocol.write(frame, self._stream)

            # check if the frame is the last frame
            if frame.end_stream:
                # close the stream
                if frame.frame_type != Http2FrameType.DATA:
                    self._stream.close_local()
                break

    def stop(self) -> None:
        """
        Stop the frame writer loop.
        This cancels the asyncio task that runs the _frame_writer_loop coroutine.
        """
        if self._send_frame_task:
            self._send_frame_task.cancel()
