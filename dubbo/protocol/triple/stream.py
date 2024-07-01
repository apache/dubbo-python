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
from typing import List, Tuple


class Stream:
    """
    Stream is a bi-directional channel that manipulates the data flow between peers.
    Inbound data from remote peer is acquired by Stream.Listener.
    Outbound data to remote peer is sent directly by Stream.
    """

    def __init__(self, stream_id: int):
        self._stream_id = stream_id

    def send_headers(self, headers: List[Tuple[str, str]]) -> None:
        """
        First call: head frame
        Second call: trailer frame.
        Args:
            headers: The headers to send.
        """
        raise NotImplementedError("send_headers() is not implemented")

    def send_data(self, data: bytes) -> None:
        """
        Send the data frame
        Args:
            data: The data to send.
        """
        raise NotImplementedError("send_data() is not implemented")

    def send_end_stream(self) -> None:
        """
        Send the end stream frame -> An empty data frame will be sent (end_stream=True)
        """
        raise NotImplementedError("send_completed() is not implemented")

    class Listener:
        """
        Listener is the interface that receives the data from the stream.
        """

        def on_headers(self, headers: List[Tuple[str, str]]) -> None:
            """
            Called when the header frame is received
            Args:
                headers: The headers received.
            """
            raise NotImplementedError("receive_headers() is not implemented")

        def on_data(self, data: bytes) -> None:
            """
            Called when the data frame is received
            Args:
                data: The data received.
            """
            raise NotImplementedError("receive_data() is not implemented")

        def on_complete(self) -> None:
            """
            Complete the stream.
            """
            raise NotImplementedError("complete() is not implemented")


class ClientStream(Stream):
    """
    ClientStream is a Stream that is initiated by the client.
    """

    pass

    class Listener(Stream.Listener):
        """
        Listener is the interface that receives the data from the stream.
        """

        def on_trailers(self, headers: List[Tuple[str, str]]) -> None:
            """
            Called when the trailers frame is received
            Args:
                headers: The trailers received.
            """
            raise NotImplementedError("receive_trailers() is not implemented")


class ServerStream(Stream):
    """
    ServerStream is a Stream that is initiated by the server.
    """

    def send_trailers(self, trailers: List[Tuple[str, str]]) -> None:
        """
        Send the trailers frame
        Args:
            trailers: The trailers to send.
        """
        raise NotImplementedError("send_trailers() is not implemented")

    class Listener(Stream.Listener):
        """
        Listener is the interface that receives the data from the stream.
        """

        pass
