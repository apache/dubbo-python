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

from typing import Any, Optional

from dubbo.compression import Compressor, Identity
from dubbo.loggers import loggerFactory
from dubbo.protocol.triple.call import ClientCall
from dubbo.protocol.triple.constants import GRpcCode
from dubbo.protocol.triple.metadata import RequestMetadata
from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.protocol.triple.stream import ClientStream
from dubbo.protocol.triple.stream.client_stream import TriClientStream
from dubbo.remoting.aio.http2.stream_handler import StreamClientMultiplexHandler
from dubbo.serialization import Deserializer, SerializationError, Serializer

__all__ = [
    "TripleClientCall",
    "FutureToClientCallListenerAdapter",
    "ReadStreamToClientCallListenerAdapter",
]

from dubbo.utils import FunctionHelper

_LOGGER = loggerFactory.get_logger()


class TripleClientCall(ClientCall, ClientStream.Listener):
    """
    Triple client call.
    """

    def __init__(
        self,
        stream_factory: StreamClientMultiplexHandler,
        listener: ClientCall.Listener,
        serializer: Serializer,
        deserializer: Deserializer,
    ):
        self._stream_factory = stream_factory
        self._client_stream: Optional[ClientStream] = None
        self._listener = listener
        self._serializer = serializer
        self._deserializer = deserializer
        self._compressor: Optional[Compressor] = None

        self._headers_sent = False
        self._done = False
        self._request_metadata: Optional[RequestMetadata] = None

    def start(self, metadata: RequestMetadata) -> None:
        self._request_metadata = metadata

        # get compression from metadata
        self._compressor = metadata.compressor

        # create a new stream
        client_stream = TriClientStream(self, self._compressor)
        h2_stream = self._stream_factory.create(client_stream.transport_listener)
        client_stream.bind(h2_stream)
        self._client_stream = client_stream

    def send_message(self, message: Any, last: bool) -> None:
        if self._done:
            _LOGGER.warning("Call is done, cannot send message")
            return

        # check if headers are sent
        if not self._headers_sent:
            # send headers
            self._headers_sent = True
            self._client_stream.send_headers(self._request_metadata.to_headers())

        # send message
        try:
            data = FunctionHelper.call_func(self._serializer.serialize, message) if message else b""
            compress_flag = 0 if self._compressor.get_message_encoding() == Identity.get_message_encoding() else 1
            self._client_stream.send_message(data, compress_flag, last)
        except SerializationError as e:
            _LOGGER.error("Failed to serialize message: %s", e)
            # close the stream
            self.cancel_by_local(e)
            # close the listener
            status = TriRpcStatus(
                code=GRpcCode.INTERNAL,
                description="Failed to serialize message",
            )
            self._listener.on_close(status, {})

    def cancel_by_local(self, e: Exception) -> None:
        if self._done:
            return
        self._done = True

        if not self._client_stream or not self._headers_sent:
            return

        status = TriRpcStatus(
            code=GRpcCode.CANCELLED,
            description=f"Call cancelled by client: {e}",
        )
        self._client_stream.cancel_by_local(status)

    def on_message(self, data: bytes) -> None:
        """
        Called when a message is received from server.
        :param data: The message data
        :type data: bytes
        """
        if self._done:
            _LOGGER.warning("Call is done, cannot receive message")
            return

        try:
            # Deserialize the message
            message = self._deserializer.deserialize(data)
            self._listener.on_message(message)
        except SerializationError as e:
            _LOGGER.error("Failed to deserialize message: %s", e)
            # close the stream
            self.cancel_by_local(e)
            # close the listener
            status = TriRpcStatus(
                code=GRpcCode.INTERNAL,
                description="Failed to deserialize message",
            )
            self._listener.on_close(status, {})

    def on_complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        """
        Called when the call is completed.
        :param status: The status
        :type status: TriRpcStatus
        :param attachments: The attachments
        :type attachments: Dict[str, Any]
        """
        if not self._done:
            self._done = True
            self._listener.on_close(status, attachments)

    def on_cancel_by_remote(self, status: TriRpcStatus) -> None:
        """
        Called when the call is cancelled by remote.
        :param status: The status
        :type status: TriRpcStatus
        """
        self.on_complete(status, {})


class FutureToClientCallListenerAdapter(ClientCall.Listener):
    """
    The future call listener.
    """

    def __init__(self, future):
        self._future = future
        self._message = None

    def on_message(self, message: Any) -> None:
        self._message = message

    def on_close(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        if status.code != GRpcCode.OK:
            self._future.set_exception(status.as_exception())
        else:
            self._future.set_result(self._message)


class ReadStreamToClientCallListenerAdapter(ClientCall.Listener):
    """
    Adapter from stream to client call listener.
    """

    def __init__(self, read_stream):
        self._read_stream = read_stream

    def on_message(self, message: Any) -> None:
        self._read_stream.put(message)

    def on_close(self, status: TriRpcStatus, trailers: dict[str, Any]) -> None:
        if status.code != GRpcCode.OK:
            self._read_stream.put_exception(status.as_exception())
        else:
            self._read_stream.put_eof()
