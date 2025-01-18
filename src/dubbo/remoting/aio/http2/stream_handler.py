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
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from dubbo.loggers import loggerFactory
from dubbo.remoting.aio.http2.frames import UserActionFrames
from dubbo.remoting.aio.http2.registries import Http2FrameType
from dubbo.remoting.aio.http2.stream import DefaultHttp2Stream, Http2Stream

_all__ = [
    "StreamMultiplexHandler",
    "StreamClientMultiplexHandler",
    "StreamServerMultiplexHandler",
]

_LOGGER = loggerFactory.get_logger()


class StreamMultiplexHandler:
    """
    The StreamMultiplexHandler class is responsible for managing the HTTP/2 streams.
    """

    __slots__ = ["_loop", "_protocol", "_streams", "_executor"]

    def __init__(self):
        # Import the Http2Protocol class here to avoid circular imports.
        from dubbo.remoting.aio.http2.protocol import AbstractHttp2Protocol

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._protocol: Optional[AbstractHttp2Protocol] = None

        # The map of stream_id to stream.
        self._streams: Optional[dict[int, DefaultHttp2Stream]] = None

        # The executor for handling received frames.
        self._executor = ThreadPoolExecutor(thread_name_prefix=f"dubbo_tri_stream_{str(uuid.uuid4())}")

    def do_init(self, loop: asyncio.AbstractEventLoop, protocol) -> None:
        """
        Initialize the StreamMultiplexHandler.\
        :param loop: The event loop.
        :type loop: asyncio.AbstractEventLoop
        :param protocol: The HTTP/2 protocol.
        :type protocol: Http2Protocol
        """
        self._loop = loop
        self._protocol = protocol
        self._streams = {}

    def put_stream(self, stream_id: int, stream: DefaultHttp2Stream) -> None:
        """
        Put the stream into the stream map.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :param stream: The stream.
        :type stream: DefaultHttp2Stream
        """
        self._streams[stream_id] = stream

    def get_stream(self, stream_id: int) -> Optional[DefaultHttp2Stream]:
        """
        Get the stream by stream identifier.
        :param stream_id: The stream identifier.
        :type stream_id: int
        :return: The stream.
        """
        return self._streams.get(stream_id)

    def remove_stream(self, stream_id: int) -> None:
        """
        Remove the stream by stream identifier.
        :param stream_id: The stream identifier.
        :type stream_id: int
        """
        self._streams.pop(stream_id, None)

    def handle_frame(self, frame: UserActionFrames) -> None:
        """
        Handle the HTTP/2 frame.
        :param frame: The HTTP/2 frame.
        :type frame: UserActionFrames
        """
        stream = self._streams.get(frame.stream_id)
        if stream:
            # It must be ensured that the event loop is not blocked,
            # and if there is a blocking operation, the executor must be used.
            stream.receive_frame(frame)

            if frame.end_stream and stream.local_closed:
                self.remove_stream(frame.stream_id)
        else:
            _LOGGER.warning("Stream %s not found. Ignoring frame %s", frame.stream_id, frame)

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
        return DefaultHttp2Stream(-1, listener, self._loop, self._protocol, self._executor)


class StreamServerMultiplexHandler(StreamMultiplexHandler):
    """
    The StreamServerMultiplexHandler class is responsible for managing the HTTP/2 streams on the server side.
    """

    __slots__ = ["_listener_factory"]

    def __init__(
        self,
        listener_factory: Callable[[], Http2Stream.Listener],
    ):
        super().__init__()
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
        new_stream = DefaultHttp2Stream(stream_id, stream_listener, self._loop, self._protocol, self._executor)
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
