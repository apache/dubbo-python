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
from concurrent.futures import Future as ThreadingFuture
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.h2_frame import H2Frame, H2FrameType
from dubbo.remoting.aio.h2_stream import Stream

logger = loggerFactory.get_logger(__name__)


class StreamHandler:
    """
    Stream handler class. It is used to handle the stream in the connection.
    Args:
        executor(ThreadPoolExecutor): The executor to handle the frame.
    """

    def __init__(
        self,
        executor: Optional[ThreadPoolExecutor] = None,
    ):
        # import here to avoid circular import
        from dubbo.remoting.aio.h2_protocol import H2Protocol

        self._protocol: Optional[H2Protocol] = None

        # The event loop to run the asynchronous function.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # The streams managed by the handler
        self._streams: Dict[int, Stream] = {}

        # The executor to handle the frame, If None, the default executor will be used.
        self._executor = executor

    def init(self, loop: asyncio.AbstractEventLoop, protocol) -> None:
        """
        Initialize the handler with the protocol.
        Args:
            loop(asyncio.AbstractEventLoop): The event loop.
            protocol(H2Protocol): The protocol.
        """
        self._loop = loop
        self._protocol = protocol
        self._streams.clear()

    def handle_frame(self, frame: H2Frame) -> None:
        """
        Handle the frame received from the connection.
        Args:
            frame: The frame to handle.
        """
        # Handle the frame in the executor
        self._loop.run_in_executor(self._executor, self._handle_in_executor, frame)

    def _handle_in_executor(self, frame: H2Frame) -> None:
        """
        Actually handle the frame in the executor.
        Args:
            frame: The frame to handle.
        """
        stream = self._streams.get(frame.stream_id)

        if not stream:
            logger.warning(f"Unknown stream: id={frame.stream_id}")
            return

        frame_type = frame.frame_type
        if frame_type == H2FrameType.HEADERS:
            stream.receive_headers(frame.data)
        elif frame_type == H2FrameType.DATA:
            stream.receive_data(frame.data)
        elif frame_type == H2FrameType.RST_STREAM:
            stream.receive_reset(frame.data)
        else:
            logger.debug(f"Unhandled frame: {frame_type}")

        if frame.end_stream:
            stream.receive_complete()

    def create(self, listener: Stream.Listener) -> Stream:
        """
        Create a new stream. -> Client
        Args:
            listener: The listener to the stream.
        Returns:
            Stream: The new stream.
        """
        raise NotImplementedError("create() is not implemented")

    def register(self, stream_id: int) -> None:
        """
        Register the stream to the handler -> Server
        Args:
            stream_id: The stream ID.
        """
        raise NotImplementedError("register() is not implemented")

    def remove(self, stream_id: int) -> None:
        """
        Remove the stream from the handler -> Server
        Args:
            stream_id: The stream ID.
        """
        del self._streams[stream_id]

    def destroy(self) -> None:
        """
        Destroy the handler.
        """
        for stream in self._streams.values():
            stream.close()
        self._streams.clear()


class ClientStreamHandler(StreamHandler):

    def create(self, listener: Stream.Listener) -> Stream:
        """
        Create a new stream. -> Client
        Args:
            listener: The listener to the stream.
        Returns:
            Stream: The new stream.
        """
        # Create a new client stream
        future = ThreadingFuture()

        def _inner_create(_future: ThreadingFuture):
            new_stream_id = self._protocol.conn.get_next_available_stream_id()
            new_stream = Stream(new_stream_id, listener, self._loop, self._protocol)
            self._streams[new_stream_id] = new_stream
            _future.set_result(new_stream)

        self._loop.call_soon_threadsafe(_inner_create, future)
        # Return the stream and the listener
        return future.result()


class ServerStreamHandler(StreamHandler):

    def register(self, stream_id: int) -> Tuple[Stream, Stream.Listener]:
        """
        Register the stream to the handler -> Server
        Args:
            stream_id: The stream ID.
        Returns:
            (Stream, Stream.Listener): A tuple containing the stream and the listener.
        """
        # TODO Create a new listener
        new_listener = Stream.Listener()
        new_stream = Stream(stream_id, new_listener, self._loop, self._protocol)
        self._streams[stream_id] = new_stream
        # Return the stream and the listener
        return new_stream, new_listener

    def handle_frame(self, frame: H2Frame) -> None:
        # Register the stream if it is a HEADERS frame and the stream is not registered.
        if (
            frame.frame_type == H2FrameType.HEADERS
            and frame.stream_id not in self._streams
        ):
            self.register(frame.stream_id)
        super().handle_frame(frame)
