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
from concurrent import futures
from typing import Dict, Optional

from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.exceptions import ProtocolException
from dubbo.remoting.aio.http2.frames import Http2Frame
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import Http2Stream, StreamListener

logger = loggerFactory.get_logger(__name__)


class StreamMultiplexHandler:
    """
    The StreamMultiplexHandler class is responsible for managing the HTTP/2 streams.
    """

    def __init__(self, executor: Optional[futures.ThreadPoolExecutor] = None):
        # Import the Http2Protocol class here to avoid circular imports.
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._protocol: Optional[Http2Protocol] = None

        # The map of stream_id to stream.
        self._streams: Optional[Dict[int, Http2Stream]] = None

        # The executor for handling received frames.
        self._executor = executor

    def do_init(self, loop: asyncio.AbstractEventLoop, protocol) -> None:
        """
        Initialize the StreamMultiplexHandler.\
        Args:
            loop: The asyncio event loop.
            protocol: The HTTP/2 protocol.
        """
        self._loop = loop
        self._protocol = protocol
        self._streams = {}

    def put_stream(self, stream_id: int, stream: Http2Stream) -> None:
        """
        Put the stream into the stream map.
        Args:
            stream_id: The stream identifier.
            stream: The stream.
        """
        self._streams[stream_id] = stream

    def get_stream(self, stream_id: int) -> Optional[Http2Stream]:
        """
        Get the stream by stream identifier.
        Args:
            stream_id: The stream identifier.
        Returns:
            The stream.
        """
        return self._streams.get(stream_id)

    def remove_stream(self, stream_id: int) -> None:
        """
        Remove the stream by stream identifier.
        Args:
            stream_id: The stream identifier.
        """
        self._streams.pop(stream_id, None)

    def handle_frame(self, frame: Http2Frame) -> None:
        """
        Handle the HTTP/2 frame.
        Args:
            frame: The HTTP/2 frame.
        """
        if stream := self._streams.get(frame.stream_id):
            # Handle the frame in the executor.
            self._handle_frame_in_executor(stream, frame)
        else:
            logger.warning(
                f"Stream {frame.stream_id} not found. Ignoring frame {frame}"
            )

    def _handle_frame_in_executor(self, stream: Http2Stream, frame: Http2Frame) -> None:
        """
        Handle the HTTP/2 frame in the executor.
        Args:
            frame: The HTTP/2 frame.
        """
        self._loop.run_in_executor(self._executor, stream.receive_frame, frame)

    def destroy(self) -> None:
        """
        Destroy the StreamMultiplexHandler.
        """
        self._streams = None
        self._protocol = None
        self._loop = None


class StreamClientMultiplexHandler(StreamMultiplexHandler):
    """
    The StreamClientMultiplexHandler class is responsible for managing the HTTP/2 streams on the client side.
    """

    def create(self, listener: StreamListener) -> Http2Stream:
        """
        Create a new stream.
        Returns:
            The created stream.
        """
        future = futures.Future()
        self._protocol.get_next_stream_id(future)
        try:
            # block until the stream_id is created
            stream_id = future.result()
            self._streams[stream_id] = Http2Stream(
                stream_id, listener, self._loop, self._protocol
            )
        except Exception as e:
            raise ProtocolException("Failed to create stream.") from e

        return self._streams[stream_id]


class StreamServerMultiplexHandler(StreamMultiplexHandler):
    """
    The StreamServerMultiplexHandler class is responsible for managing the HTTP/2 streams on the server side.
    """

    def register(self, stream_id: int) -> Http2Stream:
        """
        Register the stream.
        Args:
            stream_id: The stream identifier.
        Returns:
            The created stream.
        """
        stream = Http2Stream(stream_id, StreamListener(), self._loop, self._protocol)
        self._streams[stream_id] = stream
        return stream

    def handle_frame(self, frame: Http2Frame) -> None:
        """
        Handle the HTTP/2 frame.
        Args:
            frame: The HTTP/2 frame.
        """
        # Register the stream if the frame is a HEADERS frame.
        if frame.frame_type == Http2FrameType.HEADERS:
            self.register(frame.stream_id)

        # Handle the frame.
        super().handle_frame(frame)
