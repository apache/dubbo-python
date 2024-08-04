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
from typing import Callable, Dict, Optional

from dubbo.logger import loggerFactory
from dubbo.remoting.aio.exceptions import ProtocolError
from dubbo.remoting.aio.http2.frames import UserActionFrames
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import DefaultHttp2Stream, Http2Stream

_LOGGER = loggerFactory.get_logger(__name__)

_all__ = [
    "StreamMultiplexHandler",
    "StreamClientMultiplexHandler",
    "StreamServerMultiplexHandler",
]


class StreamMultiplexHandler:
    """
    The StreamMultiplexHandler class is responsible for managing the HTTP/2 streams.
    """

    __slots__ = ["_loop", "_protocol", "_streams", "_executor"]

    def __init__(self, executor: Optional[futures.ThreadPoolExecutor] = None):
        # Import the Http2Protocol class here to avoid circular imports.
        from dubbo.remoting.aio.http2.protocol import Http2Protocol

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._protocol: Optional[Http2Protocol] = None

        # The map of stream_id to stream.
        self._streams: Optional[Dict[int, DefaultHttp2Stream]] = None

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

    def put_stream(self, stream_id: int, stream: DefaultHttp2Stream) -> None:
        """
        Put the stream into the stream map.
        Args:
            stream_id: The stream identifier.
            stream: The stream.
        """
        self._streams[stream_id] = stream

    def get_stream(self, stream_id: int) -> Optional[DefaultHttp2Stream]:
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

    def handle_frame(self, frame: UserActionFrames) -> None:
        """
        Handle the HTTP/2 frame.
        Args:
            frame: The HTTP/2 frame.
        """
        stream = self._streams.get(frame.stream_id)
        if stream:
            # It must be ensured that the event loop is not blocked,
            # and if there is a blocking operation, the executor must be used.
            stream.receive_frame(frame)
        else:
            _LOGGER.warning(
                f"Stream {frame.stream_id} not found. Ignoring frame {frame}"
            )

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

    def create(self, listener: Http2Stream.Listener) -> DefaultHttp2Stream:
        """
        Create a new stream.
        :param listener: The stream listener.
        :type listener: Http2Stream.Listener
        :return: The stream.
        :rtype: DefaultHttp2Stream
        """
        future = futures.Future()
        self._protocol.get_next_stream_id(future)
        try:
            # block until the stream_id is created
            stream_id = future.result()
            new_stream = DefaultHttp2Stream(
                stream_id, listener, self._loop, self._protocol, self._executor
            )
            self.put_stream(stream_id, new_stream)
        except Exception as e:
            raise ProtocolError("Failed to create stream.") from e

        return new_stream


class StreamServerMultiplexHandler(StreamMultiplexHandler):
    """
    The StreamServerMultiplexHandler class is responsible for managing the HTTP/2 streams on the server side.
    """

    __slots__ = ["_listener_factory"]

    def __init__(
        self,
        listener_factory: Callable[[], Http2Stream.Listener],
        executor: Optional[futures.ThreadPoolExecutor] = None,
    ):
        super().__init__(executor)
        self._listener_factory = listener_factory

    def register(self, stream_id: int) -> DefaultHttp2Stream:
        """
        Register the stream.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :return: The stream.
        :rtype: DefaultHttp2Stream
        """
        stream_listener = self._listener_factory()
        new_stream = DefaultHttp2Stream(
            stream_id, stream_listener, self._loop, self._protocol, self._executor
        )
        self.put_stream(stream_id, new_stream)
        return new_stream

    def handle_frame(self, frame: UserActionFrames) -> None:
        """
        Handle the HTTP/2 frame.
        :param frame: The HTTP/2 frame.
        """
        # Register the stream if the frame is a HEADERS frame.
        if frame.frame_type == Http2FrameType.HEADERS:
            self.register(frame.stream_id)

        # Handle the frame.
        super().handle_frame(frame)
