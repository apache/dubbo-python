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
from dubbo.remoting.aio.h2_frame import (DATA_COMPLETED_FRAME, H2Frame,
                                         H2FrameType, H2FrameUtils)

logger = loggerFactory.get_logger(__name__)


class StreamFrameControl:
    """
        This class is responsible for controlling the order and sending of frames in an HTTP/2 stream.
        It ensures that frames are sent in the correct sequence, specifically HEADERS, DATA (0 or more),
        and optional TRAILERS.

        Note:
            1.
             This class is not thread-safe and does not need to be designed as thread-safe because it
             is used only within a single Stream object. However, asynchronous call safety must be ensured.
            2. Special frames like RESET can be sent without following this sequence.
            3. Each Stream object corresponds to a StreamFrameControl object.


    Args:
        protocol(H2Protocol): The protocol instance used to send frames.
        loop(asyncio.AbstractEventLoop): The asyncio event loop.
    """

    def __init__(self, protocol, loop: asyncio.AbstractEventLoop):
        # Import here to avoid looping imports
        from dubbo.remoting.aio.h2_protocol import H2Protocol

        # The protocol instance used to send frames.
        self._protocol: H2Protocol = protocol

        # The asyncio event loop.
        self._loop = loop

        # The queue for storing frames
        # HEADERS: 0, DATA: 1, TRAILERS: 2
        self._frame_queue = asyncio.PriorityQueue()

        # The event for the start of the stream -> Ensure that HEADERS frame have been placed in the queue
        self._start_event: asyncio.Event = asyncio.Event()

        # The event for the headers frame -> Ensure that HEADERS frame have been sent
        self._headers_event: Optional[asyncio.Event] = None

        # The event for the data frame -> Ensure that previous DATA frame have been sent
        self._data_event: Optional[asyncio.Event] = None

        # The flag to indicate whether the data is completed -> Ensure that all data frames have been placed in the queue
        self._data_completed = False

        # TRAILERS frame storage
        self._trailers_frame: Optional[H2Frame] = None

        self._frame_sender_loop_task = None

    def start(self):
        """
        Start the frame sender loop.
        This creates and starts an asyncio task that runs the _frame_sender_loop coroutine.
        """
        self._frame_sender_loop_task = self._loop.create_task(self._frame_sender_loop())

    def cancel(self):
        """
        Cancel the frame sender loop.
        This cancels the asyncio task running the _frame_sender_loop coroutine.
        """
        if self._frame_sender_loop_task:
            self._frame_sender_loop_task.cancel()

    def put_headers(self, headers_frame: H2Frame):
        """
        Put a HEADERS frame into the frame queue.

        Args:
            headers_frame (H2Frame): The HEADERS frame to be added.

        Raises:
            TypeError: If the frame is not a HEADERS frame.
        """
        if headers_frame.frame_type != H2FrameType.HEADERS:
            raise TypeError("The frame is not a HEADERS frame")

        # If the start event is not set, set it.
        if not self._start_event.is_set():
            # HEADERS
            self._frame_queue.put_nowait((0, headers_frame))
            self._start_event.set()
        else:
            # TRAILERS
            self.put_trailers_later(headers_frame)

    def put_data(self, data_frame: H2Frame):
        """
        Put a DATA frame into the frame queue.

        Args:
            data_frame (H2Frame): The DATA frame to be added.

        Raises:
            TypeError: If the frame is not a DATA frame.
            RuntimeError: If the data is completed, no more data can be sent.
        """
        if data_frame.frame_type != H2FrameType.DATA:
            raise TypeError("The frame is not a DATA frame")
        elif self._data_completed:
            raise RuntimeError("The data is completed, no more data can be sent.")

        if data_frame == DATA_COMPLETED_FRAME:
            # The data is completed
            self._data_completed = True
            if self._trailers_frame:
                # Make sure TRAILERS are sent after DATA
                self.put_trailers_now(self._trailers_frame)
        else:
            self._data_completed = data_frame.end_stream
            self._frame_queue.put_nowait((1, data_frame))

    def put_trailers_now(self, trailers_frame: H2Frame):
        """
        Immediately put a TRAILERS frame into the frame queue.

        Note: You should call this method when you don't need to send DATA.

        Args:
            trailers_frame (H2Frame): The TRAILERS frame to be added.

        Raises:
            TypeError: If the frame is not a HEADERS frame.
        """
        if trailers_frame.frame_type != H2FrameType.HEADERS:
            raise TypeError("The frame is not a HEADERS frame")

        self._frame_queue.put_nowait((2, trailers_frame))

    def put_trailers_later(self, trailers_frame: H2Frame):
        """
        Store the TRAILERS frame to be sent after all DATA frames.

        Note: When you need to send DATA, you should call this method.

        Args:
            trailers_frame (H2Frame): The TRAILERS frame to be stored.

        Raises:
            TypeError: If the frame is not a HEADERS frame.
        """
        self._trailers_frame = trailers_frame

    async def _frame_sender_loop(self):
        """
        The main loop for sending frames. This loop continuously fetches frames from the queue and sends them in the
        correct order.

        It ensures that HEADERS frames are sent before any DATA frames, and waits for the completion events of HEADERS
        and DATA frames before sending subsequent frames.

        If a frame has the end_stream flag set, the loop breaks, indicating the end of the stream.
        """
        while True:
            # Wait for the start event
            await self._start_event.wait()

            #  Get the frame from the outbound data queue -> it's a blocking operation, but asynchronous.
            priority, frame = await self._frame_queue.get()

            # If the frame is HEADERS, send the header frame directly.
            if frame.frame_type == H2FrameType.HEADERS and not self._headers_event:
                self._headers_event = self._protocol.send_headers_frame(frame)
            else:
                # Wait for HEADERS to be sent.
                await self._headers_event.wait()

                # Waiting for the previous DATA to be sent.
                if self._data_event:
                    await self._data_event.wait()

                if frame.frame_type == H2FrameType.DATA:
                    # Send the data frame and store the event.
                    self._data_event = self._protocol.send_data_frame(frame)
                elif frame.frame_type == H2FrameType.HEADERS:
                    # Send the trailers frame.
                    self._protocol.send_headers_frame(frame)

            if frame.end_stream:
                # The stream is completed. we can break the loop.
                break


class Stream:
    """
    Stream is a bidirectional channel that manipulates the data flow between peers.

    This class manages the sending and receiving of HTTP/2 frames for a single stream.
    It ensures frames are sent in the correct order and handles flow control for the stream.

    Args:
           stream_id (int): The stream identifier.
           listener (Stream.Listener): The listener for the stream to handle the received frames.
           loop (asyncio.AbstractEventLoop): The asyncio event loop.
           protocol (H2Protocol): The protocol instance used to send frames.

    """

    def __init__(
        self,
        stream_id: int,
        listener: "Stream.Listener",
        loop: asyncio.AbstractEventLoop,
        protocol,
    ):
        # import here to avoid circular import
        from dubbo.remoting.aio.h2_protocol import H2Protocol

        # The stream ID.
        self._stream_id: int = stream_id
        # The listener for the stream to handle the received frames.
        self._listener: "Stream.Listener" = listener

        # The protocol.
        self._protocol: H2Protocol = protocol

        # The asyncio event loop.
        self._loop = loop

        # The stream frame control.
        self._stream_frame_control = StreamFrameControl(protocol, loop)
        self._stream_frame_control.start()

        # The flag to indicate whether the sending is completed.
        self._send_completed = False

        # The flag to indicate whether the receiving is completed.
        self._receive_completed = False

    def send_headers(
        self, headers: List[Tuple[str, str]], end_stream: bool = False
    ) -> None:
        """
        Send the headers frame. The first call sends the head frame, the second call sends the trailer frame.

        Args:
            headers (List[Tuple[str, str]]): The headers to send.
            end_stream (bool): Whether to end the stream after sending this frame.
        """
        if self._send_completed:
            return
        else:
            self._send_completed = end_stream

        def _inner_send_headers(_headers: List[Tuple[str, str]], _end_stream: bool):
            headers_frame = H2FrameUtils.create_headers_frame(
                self._stream_id, _headers, _end_stream
            )
            self._stream_frame_control.put_headers(headers_frame)

        self._loop.call_soon_threadsafe(_inner_send_headers, headers, end_stream)
        # Try to close the stream
        self.try_close()

    def send_data(self, data: bytes, end_stream: bool = False) -> None:
        """
        Send a data frame.

        Args:
            data (bytes): The data to send.
            end_stream (bool): Whether to end the stream after sending this frame.
        """
        if self._send_completed:
            return
        else:
            self._send_completed = end_stream

        def _inner_send_data(_data: bytes, _end_stream: bool):
            data_frame = H2FrameUtils.create_data_frame(
                self._stream_id, _data, _end_stream
            )
            self._stream_frame_control.put_data(data_frame)

        self._loop.call_soon_threadsafe(_inner_send_data, data, end_stream)
        # Try to close the stream
        self.try_close()

    def send_data_completed(self) -> None:
        """
        Indicates that the data frame has been fully sent, but other frames (such as trailers) may still need to be sent.
        """

        def _inner_send_data_completed():
            self._stream_frame_control.put_data(DATA_COMPLETED_FRAME)

        self._loop.call_soon_threadsafe(_inner_send_data_completed)

    def send_reset(self, error_code: int) -> None:
        """
        Send a reset frame to terminate the stream.

        Note: This is a special frame and does not need to follow the sequence of frames.

        Args:
            error_code (int): The error code indicating the reason for the reset.
        """
        self._send_completed = True

        def _inner_send_reset(_error_code: int):
            reset_frame = H2FrameUtils.create_reset_stream_frame(
                self._stream_id, _error_code
            )
            self._protocol.send_reset_frame(reset_frame)
            self._stream_frame_control.cancel()

        self._loop.call_soon_threadsafe(_inner_send_reset, error_code)

        # Close the stream immediately.
        self.close()

    def receive_headers(self, headers: List[Tuple[str, str]]) -> None:
        """
        Called when a headers frame is received.

        Args:
            headers (List[Tuple[str, str]]): The headers received.
        """
        self._listener.on_headers(headers)

    def receive_data(self, data: bytes) -> None:
        """
        Called when a data frame is received.

        Args:
            data (bytes): The data received.
        """
        self._listener.on_data(data)

    def receive_complete(self) -> None:
        """
        Called when the stream is completed.
        """
        self._receive_completed = True
        # notify the listener
        self._listener.on_complete()
        # Try to close the stream
        self.try_close()

    def receive_reset(self, err_code: int) -> None:
        """
        Called when the stream is cancelled by the remote peer.

        Args:
            err_code (int): The error code indicating the reason for cancellation.
        """
        self._listener.on_reset(err_code)

    def try_close(self) -> None:
        """
        Try to close the stream.
        """
        if self._send_completed and self._receive_completed:
            self.close()

    def close(self) -> None:
        """
        Close the stream by cancelling the frame sender loop.
        """
        self._stream_frame_control.cancel()

    class Listener:
        """
        The listener for the stream to handle the received frames.
        """

        def on_headers(self, headers: List[Tuple[str, str]]) -> None:
            """
            Called when a headers frame is received.

            Args:
                headers (List[Tuple[str, str]]): The headers received.
            """
            raise NotImplementedError("on_headers() is not implemented")

        def on_data(self, data: bytes) -> None:
            """
            Called when a data frame is received.

            Args:
                data (bytes): The data received.
            """
            raise NotImplementedError("on_data() is not implemented")

        def on_complete(self) -> None:
            """
            Called when the stream is completed.
            """
            raise NotImplementedError("on_complete() is not implemented")

        def on_reset(self, err_code: int) -> None:
            """
            Called when the stream is cancelled by the remote peer.

            Args:
                err_code (int): The error code indicating the reason for cancellation.
            """
            raise NotImplementedError("on_reset() is not implemented")
