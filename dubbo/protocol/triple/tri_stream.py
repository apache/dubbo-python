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

    def send_headers(self, headers: List[Tuple[str, str]]) -> None:
        """
        Send the headers frame
        Args:
            headers: The headers to send.
        """
        raise NotImplementedError("send_headers() is not implemented")

    def send_data(self, stream_id: int, data: bytes, end_stream: bool = False) -> None:
        """
        Send the data frame
        Args:
            stream_id: The stream ID the data is associated with.
            data: The data to send.
            end_stream: Whether to end the stream.
        """
        raise NotImplementedError("send_data() is not implemented")

    class Listener:
        """
        Listener is the interface to receive the data flow from the remote peer
        """

        def receive_headers(
            self, stream_id: int, headers: List[Tuple[str, str]]
        ) -> None:
            """
            Called when the header frame is received
            Args:
                stream_id: The stream ID the headers are associated with.
                headers: The headers received.
            """
            raise NotImplementedError("receive_headers() is not implemented")

        def receive_data(self, stream_id: int, data: bytes) -> None:
            """
            Called when the data frame is received
            Args:
                stream_id: The stream ID the data is associated with.
                data: The data received.
            """
            raise NotImplementedError("receive_data() is not implemented")

        def receive_trailers(
            self, stream_id: int, headers: List[Tuple[str, str]]
        ) -> None:
            """
            Called when the trailers frame is received
            Args:
                stream_id: The stream ID the trailers are associated with.
                headers: The trailers received.
            """
            raise NotImplementedError("receive_trailers() is not implemented")

        def receive_end(self, stream_id: int) -> None:
            """
            Called when the stream is ended
            Args:
                stream_id: The stream ID that was ended.
            """
            raise NotImplementedError("receive_end() is not implemented")
