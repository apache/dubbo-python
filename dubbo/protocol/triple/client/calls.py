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
from typing import Any, List, Optional, Tuple

from dubbo.compressor.compression import Compression
from dubbo.protocol.triple.tri_codec import TriEncoder
from dubbo.protocol.triple.tri_results import AbstractTriResult
from dubbo.protocol.triple.tri_status import TriRpcStatus
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode
from dubbo.remoting.aio.http2.stream import Http2Stream
from dubbo.serialization import Serialization


class ClientCall:
    """
    The client call.
    """

    def __init__(self, listener: "ClientCall.Listener"):
        self._listener = listener
        self._stream: Optional[Http2Stream] = None

    def bind_stream(self, stream: Http2Stream) -> None:
        """
        Bind stream
        """
        self._stream = stream

    def send_headers(self, headers: Http2Headers) -> None:
        """
        Send headers.
        Args:
            headers: The headers.
        """
        raise NotImplementedError("send_headers() is not implemented.")

    def send_message(self, message: Any, last: bool = False) -> None:
        """
        Send message.
        Args:
            message: The message.
            last: Whether this is the last message.
        """
        raise NotImplementedError("send_message() is not implemented.")

    def send_reset(self, error_code: Http2ErrorCode) -> None:
        """
        Send a reset.
        Args:
            error_code: The error code.
        """
        raise NotImplementedError("send_reset() is not implemented.")

    class Listener:
        """
        The listener of the client call.
        """

        def on_message(self, message: Any) -> None:
            """
            Called when a message is received.
            """
            raise NotImplementedError("on_message() is not implemented.")

        def on_close(
            self, rpc_status: TriRpcStatus, trailers: List[Tuple[str, str]]
        ) -> None:
            """
            Called when the stream is closed.
            """
            raise NotImplementedError("on_close() is not implemented.")


class TriClientCall(ClientCall):
    """
    The triple client call.
    """

    def __init__(
        self,
        result: AbstractTriResult,
        serialization: Serialization,
        compression: Optional[Compression] = None,
    ):
        super().__init__(TriClientCall.Listener(result, serialization))
        self._serialization = serialization
        self._tri_encoder = TriEncoder(compression)

    @property
    def listener(self) -> "TriClientCall.Listener":
        return self._listener

    def send_headers(self, headers: Http2Headers) -> None:
        """
        Send headers.
        """
        self._stream.send_headers(headers, end_stream=False)

    def send_message(self, message: Any, last: bool = False) -> None:
        """
        Send a message.
        """
        # Serialize the message
        serialized_message = self._serialization.serialize(message)

        # Encode the message
        encode_message = self._tri_encoder.encode(serialized_message)
        self._stream.send_data(encode_message, end_stream=last)

    def send_reset(self, error_code: Http2ErrorCode) -> None:
        """
        Send a reset.
        """
        self._stream.send_reset(error_code)

    class Listener(ClientCall.Listener):
        """
        The listener of the triple client call.
        """

        def __init__(self, result: AbstractTriResult, serialization: Serialization):
            self._result = result
            self._serialization = serialization

        def on_message(self, message: Any) -> None:
            """
            Called when a message is received.
            """
            # Deserialize the message
            deserialized_message = self._serialization.deserialize(message)
            self._result.set_value(deserialized_message)

        def on_close(
            self, rpc_status: TriRpcStatus, trailers: List[Tuple[str, str]]
        ) -> None:
            """
            Called when the stream is closed.
            """
            if rpc_status.cause:
                self._result.set_exception(rpc_status.cause)
            # Notify the result that the stream is complete
            self._result.set_value(self._result.END_SIGNAL)
