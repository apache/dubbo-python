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

from typing import Optional

from dubbo.compression import Compressor, Decompressor
from dubbo.compression.identities import Identity
from dubbo.extension import ExtensionError, extensionLoader
from dubbo.protocol.triple.coders import TriDecoder, TriEncoder
from dubbo.protocol.triple.constants import (
    GRpcCode,
    TripleHeaderName,
    TripleHeaderValue,
)
from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.protocol.triple.stream import ClientStream
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode
from dubbo.remoting.aio.http2.stream import Http2Stream

__all__ = ["TriClientStream"]


class TriClientStream(ClientStream):
    """
    Triple client stream.
    """

    def __init__(
        self,
        listener: ClientStream.Listener,
        compressor: Optional[Compressor],
    ):
        """
        Initialize the triple client stream.
        :param listener: The listener.
        :type listener: ClientStream.Listener
        :param compressor: The compression.
        """
        self._transport_listener = ClientTransportListener(listener)
        self._encoder = TriEncoder(compressor)

        self._stream: Optional[Http2Stream] = None

    @property
    def transport_listener(self) -> "ClientTransportListener":
        """
        Get the transport listener.
        :return: The transport listener.
        :rtype: ClientTransportListener
        """
        return self._transport_listener

    def bind(self, stream: Http2Stream) -> None:
        """
        Bind the stream.
        :param stream: The stream to bind.
        :type stream: Http2Stream
        """
        self._stream = stream

    def send_headers(self, headers: Http2Headers) -> None:
        """
        Send headers to remote peer.
        :param headers: The headers to send.
        :type headers: Http2Headers
        """
        self._stream.send_headers(headers)

    def send_message(self, data: bytes, compress_flag: int, last: bool) -> None:
        """
        Send message to remote peer.
        :param data: The message data.
        :type data: bytes
        :param compress_flag: The compress flag (0: no compress, 1: compress).
        :type compress_flag: int
        :param last: Whether this is the last message.
        :type last: bool
        """
        # encode the data
        encoded_data = self._encoder.encode(data, compress_flag)
        self._stream.send_data(encoded_data, last)

    def cancel_by_local(self, status: TriRpcStatus) -> None:
        """
        Cancel the stream by local
        :param status: The status
        :type status: TriRpcStatus
        """
        self._stream.cancel_by_local(Http2ErrorCode.CANCEL)
        self._transport_listener.rst = True


class ClientTransportListener(Http2Stream.Listener, TriDecoder.Listener):
    """
    Client transport listener.
    """

    __slots__ = [
        "_listener",
        "_decoder",
        "_rpc_status",
        "_headers_received",
        "_rst",
    ]

    def __init__(self, listener: ClientStream.Listener):
        """
        Initialize the client transport listener.
        :param listener: The listener.
        """
        super().__init__()
        self._listener = listener

        self._decoder: Optional[TriDecoder] = None
        self._rpc_status: Optional[TriRpcStatus] = None

        self._headers_received = False
        self._rst = False

        self._trailers: Http2Headers = Http2Headers()

    @property
    def rst(self) -> bool:
        """
        Whether the stream is rest.
        :return: True if the stream is rest, otherwise False.
        :rtype: bool
        """
        return self._rst

    @rst.setter
    def rst(self, value: bool) -> None:
        """
        Set whether the stream is rest.
        :param value: True if the stream is rest, otherwise False.
        :type value: bool
        """
        self._rst = value

    def on_headers(self, headers: Http2Headers, end_stream: bool) -> None:
        if not end_stream:
            # handle headers
            self._on_headers_received(headers)
        else:
            # handle trailers
            self._on_trailers_received(headers)

        if end_stream and not self._headers_received:
            self._handle_transport_error(self._rpc_status)

    def on_data(self, data: bytes, end_stream: bool) -> None:
        if self._rpc_status:
            self._rpc_status.append_description(f"Data: {data.decode('utf-8')}")
            if len(self._rpc_status.description) > 512 or end_stream:
                self._handle_transport_error(self._rpc_status)
            return

        # decode the data
        self._decoder.decode(data)

    def cancel_by_remote(self, error_code: Http2ErrorCode) -> None:
        self.rst = True
        self._rpc_status = TriRpcStatus(
            GRpcCode.CANCELLED,
            description=f"Cancelled by remote peer, error code: {error_code}",
        )
        self._listener.on_complete(self._rpc_status, self._trailers.to_dict())

    def _on_headers_received(self, headers: Http2Headers) -> None:
        """
        Handle the headers received.
        :param headers: The headers.
        :type headers: Http2Headers
        """
        self._headers_received = True

        # validate headers
        self._validate_headers(headers)
        if self._rpc_status:
            return

        # get messageEncoding
        decompressor: Optional[Decompressor] = None
        message_encoding = headers.get(TripleHeaderName.GRPC_ENCODING.value, Identity.get_message_encoding())
        if message_encoding != Identity.get_message_encoding():
            try:
                # get decompressor by messageEncoding
                decompressor = extensionLoader.get_extension(Decompressor, message_encoding)()
            except ExtensionError:
                # unsupported
                self._rpc_status = TriRpcStatus(
                    GRpcCode.UNIMPLEMENTED,
                    description="Unsupported message encoding",
                )
                return

        self._decoder = TriDecoder(self, decompressor)

    def _validate_headers(self, headers: Http2Headers) -> None:
        """
        Validate the headers.
        :param headers: The headers.
        :type headers: Http2Headers
        """
        status_code = int(headers.status) if headers.status else None
        if status_code:
            content_type = headers.get(TripleHeaderName.CONTENT_TYPE.value, "")
            if not content_type.startswith(TripleHeaderValue.APPLICATION_GRPC.value):
                self._rpc_status = TriRpcStatus.from_http_code(status_code).with_description(
                    f"Invalid content type: {content_type}"
                )

        else:
            self._rpc_status = TriRpcStatus(GRpcCode.INTERNAL, description="Missing HTTP status code")

    def _on_trailers_received(self, trailers: Http2Headers) -> None:
        """
        Handle the trailers received.
        :param trailers: The trailers.
        :type trailers: Http2Headers
        """
        if not self._rpc_status and not self._headers_received:
            self._validate_headers(trailers)

        if self._rpc_status:
            self._rpc_status.append_description(f"Trailers: {trailers}")
        else:
            self._rpc_status = self._get_status_from_trailers(trailers)
            self._trailers = trailers

        if self._decoder:
            self._decoder.close()
        else:
            self._listener.on_complete(self._rpc_status, trailers.to_dict())

    def _get_status_from_trailers(self, trailers: Http2Headers) -> TriRpcStatus:
        """
        Validate the trailers.
        :param trailers: The trailers.
        :type trailers: Http2Headers
        :return: The RPC status.
        :rtype: TriRpcStatus
        """
        grpc_status_code = int(trailers.get(TripleHeaderName.GRPC_STATUS.value, "-1"))
        if grpc_status_code != -1:
            status = TriRpcStatus.from_rpc_code(grpc_status_code)
            message = trailers.get(TripleHeaderName.GRPC_MESSAGE.value, "")
            status.append_description(message)
            return status

        # If the status code is not found , something is broken. Try to provide a rational error.
        if self._headers_received:
            return TriRpcStatus(GRpcCode.UNKNOWN, description="Missing GRPC status in response")

        # Try to get status from headers
        status_code = int(trailers.status) if trailers.status else None
        if status_code is not None:
            status = TriRpcStatus.from_http_code(status_code)
        else:
            status = TriRpcStatus(GRpcCode.INTERNAL, description="Missing HTTP status code")

        status.append_description("Missing GRPC status, please infer the error from the HTTP status code")
        return status

    def _handle_transport_error(self, transport_error: TriRpcStatus) -> None:
        """
        Handle the transport error.
        :param transport_error: The transport error.
        :type transport_error: TriRpcStatus
        """
        self._stream.cancel_by_local(Http2ErrorCode.NO_ERROR)
        self.rst = True
        self._listener.on_complete(transport_error, self._trailers.to_dict())

    def on_message(self, message: bytes) -> None:
        """
        Called when a message is received (TriDecoder.Listener callback).
        :param message: The message received.
        """
        self._listener.on_message(message)

    def close(self) -> None:
        """
        Called when the stream is closed (TriDecoder.Listener callback).
        """
        self._listener.on_complete(self._rpc_status, self._trailers.to_dict())
