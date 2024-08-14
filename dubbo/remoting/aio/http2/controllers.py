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
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, Optional, Set

from h2.connection import H2Connection

from dubbo.loggers import loggerFactory
from dubbo.remoting.aio.http2.frames import (
    DataFrame,
    HeadersFrame,
    UserActionFrames,
    WindowUpdateFrame,
)
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import DefaultHttp2Stream, Http2Stream
from dubbo.utils import EventHelper

__all__ = ["RemoteFlowController", "FrameInboundController", "FrameOutboundController"]

_LOGGER = loggerFactory.get_logger()


class Controller(abc.ABC):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task] = None
        self._started = False
        self._closed = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._task = self._loop.create_task(self._run())
            self._started = True

    @abc.abstractmethod
    async def _run(self) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        with self._lock:
            if self._closed or not self._task:
                return
            self._task.cancel()
            self._task = None


class RemoteFlowController(Controller):
    @dataclass
    class Item:
        stream: Http2Stream
        data: bytearray
        end_stream: bool
        event: Optional[asyncio.Event]

    def __init__(
        self,
        h2_connection: H2Connection,
        transport: asyncio.Transport,
        loop: asyncio.AbstractEventLoop,
    ):
        super().__init__(loop)
        self._h2_connection = h2_connection
        self._transport = transport

        self._stream_dict: Dict[int, RemoteFlowController.Item] = {}

        self._outbound_queue: asyncio.Queue[int] = asyncio.Queue()
        self._flow_controls: Set[int] = set()

        # Start the controller
        self.start()

    def write_data(
        self, stream: Http2Stream, frame: DataFrame, event: Optional[asyncio.Event]
    ) -> None:
        if stream.local_closed:
            EventHelper.set(event)
            _LOGGER.warning(f"Stream {stream.id} is closed.")
            return

        item = self._stream_dict.get(stream.id)
        if item:
            # Extend the data if the stream item exists
            item.data.extend(frame.data)
            item.end_stream = frame.end_stream
            # update the event
            EventHelper.set(item.event)
            item.event = event
        else:
            # Create a new stream item
            item = RemoteFlowController.Item(
                stream, bytearray(frame.data), frame.end_stream, event
            )
            self._stream_dict[stream.id] = item
            self._outbound_queue.put_nowait(stream.id)

    def release_flow_control(self, frame: WindowUpdateFrame) -> None:
        stream_id = frame.stream_id
        if stream_id is None or stream_id == 0:
            # This is for the entire connection.
            for i in self._flow_controls:
                self._outbound_queue.put_nowait(i)
            self._flow_controls.clear()
        elif stream_id in self._flow_controls:
            # This is specific to a single stream.
            self._flow_controls.remove(stream_id)
            self._outbound_queue.put_nowait(stream_id)

    async def _run(self) -> None:
        while True:
            # get the data to send.(async blocking)
            stream_id = await self._outbound_queue.get()

            # check if the stream is closed
            item = self._stream_dict[stream_id]
            stream = item.stream
            if stream.local_closed:
                # The local side of the stream is closed, so we don't need to send any data.
                EventHelper.set(item.event)
                continue

            # get the flow control window size
            data = item.data
            window_size = self._h2_connection.local_flow_control_window(stream.id)
            chunk_size = min(window_size, len(data))
            data_to_send = data[:chunk_size]
            data_to_buffer = data[chunk_size:]

            # send the data
            if data_to_send or item.end_stream:
                max_size = self._h2_connection.max_outbound_frame_size
                # Split the data into chunks and send them out
                for x in range(0, len(data_to_send), max_size):
                    chunk = data_to_send[x : x + max_size]
                    end_stream_flag = (
                        item.end_stream
                        and not data_to_buffer
                        and (x + max_size >= len(data_to_send))
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
                item.data = data_to_buffer
                self._flow_controls.add(stream.id)
            else:
                # If all data has been sent, trigger the event.
                self._stream_dict.pop(stream.id)
                EventHelper.set(item.event)
                if item.end_stream:
                    stream.close_local()


class FrameInboundController(Controller):
    """
    HTTP/2 frame inbound controller.
    This class is responsible for reading frames in the correct order.
    """

    def __init__(
        self,
        stream: Http2Stream,
        loop: asyncio.AbstractEventLoop,
        protocol,
        executor: Optional[ThreadPoolExecutor] = None,
    ):
        """
        Initialize the FrameInboundController.
        :param stream: The stream.
        :type stream: Http2Stream
        :param loop: The asyncio event loop.
        :type loop: asyncio.AbstractEventLoop
        :param protocol: The HTTP/2 protocol.
        :param executor: The thread pool executor for handling frames.
        :type executor: Optional[ThreadPoolExecutor]
        """
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        super().__init__(loop)

        self._stream = stream
        self._protocol: Http2Protocol = protocol
        self._executor = executor

        # The queue for receiving frames.
        self._inbound_queue: asyncio.Queue[UserActionFrames] = asyncio.Queue()

        self._condition: asyncio.Condition = asyncio.Condition()

        # Start the controller
        self.start()

    def write_frame(self, frame: UserActionFrames) -> None:
        """
        Put the frame into the frame queue (thread-unsafe).
        :param frame: The HTTP/2 frame to put into the queue.
        """
        self._inbound_queue.put_nowait(frame)

    def ack_frame(self, frame: UserActionFrames) -> None:
        """
        Acknowledge the frame by setting the frame event.(thread-safe)
        """

        async def _inner_operation(_frame: UserActionFrames):
            async with self._condition:
                if _frame.frame_type == Http2FrameType.DATA:
                    self._protocol.ack_received_data(_frame.stream_id, _frame.padding)
                self._condition.notify_all()

        asyncio.run_coroutine_threadsafe(_inner_operation(frame), self._loop)

    async def _run(self) -> None:
        """
        Coroutine that continuously reads frames from the frame queue.
        """
        while True:
            async with self._condition:
                # get the frame from the queue
                frame = await self._inbound_queue.get()

                if self._stream.remote_closed:
                    # The remote side of the stream is closed, so we don't need to process any more frames.
                    break

                # handle frame in the thread pool
                self._loop.run_in_executor(self._executor, self._handle_frame, frame)

                if not frame.end_stream:
                    # Waiting for the previous frame to be processed
                    await self._condition.wait()
                else:
                    # close the stream remotely
                    self._stream.close_remote()
                    break

    def _handle_frame(self, frame: UserActionFrames):
        listener = self._stream.listener
        # match the frame type
        frame_type = frame.frame_type
        if frame_type == Http2FrameType.HEADERS:
            listener.on_headers(frame.headers, frame.end_stream)
        elif frame_type == Http2FrameType.DATA:
            listener.on_data(frame.data, frame.end_stream)
        elif frame_type == Http2FrameType.RST_STREAM:
            listener.cancel_by_remote(frame.error_code)
        else:
            _LOGGER.warning(f"unprocessed frame type: {frame.frame_type}")

        # acknowledge the frame
        self.ack_frame(frame)


class FrameOutboundController(Controller):
    """
    HTTP/2 frame outbound controller.
    This class is responsible for writing frames in the correct order.
    """

    LAST_DATA_FRAME = DataFrame(-1, b"", 0)

    def __init__(
        self, stream: DefaultHttp2Stream, loop: asyncio.AbstractEventLoop, protocol
    ):
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        super().__init__(loop)

        self._stream = stream
        self._protocol: Http2Protocol = protocol

        self._headers_put_event: asyncio.Event = asyncio.Event()
        self._headers_sent_event: asyncio.Event = asyncio.Event()
        self._headers: Optional[HeadersFrame] = None

        self._data_queue: asyncio.Queue[DataFrame] = asyncio.Queue()
        self._data_sent_event: asyncio.Event = asyncio.Event()

        self._trailers: Optional[HeadersFrame] = None

        # Start the controller
        self.start()

    def write_headers(self, frame: HeadersFrame) -> None:
        """
        Write the headers frame by order.(thread-safe)
        :param frame: The headers frame.
        :type frame: HeadersFrame
        """

        def _inner_operation(_frame: HeadersFrame):
            if not self._headers:
                # send the frame directly -> the headers frame is the first frame
                self._headers = _frame
                EventHelper.set(self._headers_put_event)
            else:
                # put the frame into the queue -> the headers frame is not the first frame(trailers)
                self._trailers = _frame
                # Notify the data queue that the last data frame has reached.
                self._data_queue.put_nowait(FrameOutboundController.LAST_DATA_FRAME)

        self._loop.call_soon_threadsafe(_inner_operation, frame)

    def write_data(self, frame: DataFrame) -> None:
        """
        Write the data frame by order.(thread-safe)
        :param frame: The data frame.
        :type frame: DataFrame
        """
        self._loop.call_soon_threadsafe(self._data_queue.put_nowait, frame)

    def write_rst(self, frame: UserActionFrames) -> None:
        """
        Write the reset frame directly.(thread-safe)
        :param frame: The reset frame.
        :type frame: UserActionFrames
        """

        def _inner_operation(_frame: UserActionFrames):
            self._protocol.send_frame(_frame, self._stream)

            self._stream.close_local()
            self._stream.close_remote()

        self._loop.call_soon_threadsafe(_inner_operation, frame)

    async def _run(self) -> None:
        """
        Coroutine that continuously writes frames from the frame queue.
        """

        # wait and send the headers frame
        await self._headers_put_event.wait()
        self._protocol.send_frame(self._headers, self._stream, self._headers_sent_event)

        # check if the headers frame is the last frame
        if self._headers.end_stream:
            self._stream.close_local()
            return

        # wait for the headers sent event
        await self._headers_sent_event.wait()

        # wait and send the data frames
        while True:
            frame = await self._data_queue.get()
            if frame is not FrameOutboundController.LAST_DATA_FRAME:
                self._data_sent_event = asyncio.Event()
                self._protocol.send_frame(frame, self._stream, self._data_sent_event)
                if frame.end_stream:
                    # The last frame has been sent, so the stream is closed.
                    return
            else:
                # The last frame has been reached.
                break

        # wait for the last data frame and send the trailers frame
        await self._data_sent_event.wait()
        self._protocol.send_frame(self._trailers, self._stream)

        # close the stream
        self._stream.close_local()
