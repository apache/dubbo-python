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
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from dubbo.compression import Decompressor
from dubbo.compression.identities import Identity
from dubbo.extension import ExtensionError, extensionLoader
from dubbo.loggers import loggerFactory
from dubbo.protocol.triple.call.server_call import TripleServerCall
from dubbo.protocol.triple.coders import TriDecoder, TriEncoder
from dubbo.protocol.triple.constants import (
    GRpcCode,
    TripleHeaderName,
    TripleHeaderValue,
)
from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.protocol.triple.stream import ServerStream
from dubbo.proxy.handlers import RpcMethodHandler, RpcServiceHandler
from dubbo.remoting.aio.http2.headers import Http2Headers, HttpMethod
from dubbo.remoting.aio.http2.registries import Http2ErrorCode, HttpStatus
from dubbo.remoting.aio.http2.stream import Http2Stream

__all__ = ["ServerTransportListener", "TripleServerStream"]

_LOGGER = loggerFactory.get_logger()


class TripleServerStream(ServerStream):
    def __init__(self, stream: Http2Stream):
        self._stream = stream

        self._tri_encoder = TriEncoder(Identity())

        self._rst = False
        self._headers_sent = False
        self._trailers_sent = False

    @property
    def rst(self) -> bool:
        return self._rst

    @rst.setter
    def rst(self, value: bool) -> None:
        self._rst = value

    @property
    def headers_sent(self) -> bool:
        return self._headers_sent

    @property
    def trailers_sent(self) -> bool:
        return self._trailers_sent

    def set_compression(self, compression: str) -> None:
        if compression == Identity.get_message_encoding():
            return
        try:
            decompressor = extensionLoader.get_extension(Decompressor, compression)()
            self._tri_encoder.compressor = decompressor
        except ExtensionError:
            _LOGGER.warning("Unsupported compression: %s", compression)
            self.cancel_by_local(TriRpcStatus(GRpcCode.INTERNAL, description="Unsupported compression"))

    def send_headers(self, headers: Http2Headers) -> None:
        if not self.headers_sent:
            self._stream.send_headers(headers)
            self._headers_sent = True

    def send_message(self, data: bytes, compress_flag: bool) -> None:
        # encode the message
        encoded_data = self._tri_encoder.encode(data, compress_flag)
        self._stream.send_data(encoded_data, end_stream=False)

    def complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        trailers = Http2Headers()
        if not self.headers_sent:
            trailers.status = HttpStatus.OK.value
            trailers.add(
                TripleHeaderName.CONTENT_TYPE.value,
                TripleHeaderValue.APPLICATION_GRPC_PROTO.value,
            )

        # add attachments
        [trailers.add(k, v) for k, v in attachments.items()]

        # add status
        trailers.add(TripleHeaderName.GRPC_STATUS.value, status.code.value)
        if status.code is not GRpcCode.OK:
            trailers.add(
                TripleHeaderName.GRPC_MESSAGE.value,
                TriRpcStatus.limit_desc(status.description),
            )

        # send trailers
        self._headers_sent = True
        self._trailers_sent = True
        self._stream.send_headers(trailers, end_stream=True)

    def cancel_by_local(self, status: TriRpcStatus) -> None:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Cancel stream: %s, status: %s", self._stream.id, status)

        if not self._rst:
            self._rst = True
            self._stream.cancel_by_local(Http2ErrorCode.CANCEL)


class ServerTransportListener(Http2Stream.Listener):
    """
    ServerTransportListener is a callback interface that receives events on the stream.
    """

    def __init__(
        self,
        service_handles: dict[str, RpcServiceHandler],
        method_executor: ThreadPoolExecutor,
    ):
        super().__init__()
        self._listener: Optional[ServerStream.Listener] = None
        self._decoder: Optional[TriDecoder] = None
        self._service_handles = service_handles
        self._executor: Optional[ThreadPoolExecutor] = method_executor

    def on_headers(self, headers: Http2Headers, end_stream: bool) -> None:
        # check http method
        if headers.method != HttpMethod.POST.value:
            self._response_plain_text_error(
                HttpStatus.METHOD_NOT_ALLOWED.value,
                TriRpcStatus(
                    GRpcCode.INTERNAL,
                    description=f"Method {headers.method} is not supported",
                ),
            )
            return

        # check content type
        content_type = headers.get(TripleHeaderName.CONTENT_TYPE.value, "")
        if not content_type.startswith(TripleHeaderValue.APPLICATION_GRPC.value):
            self._response_plain_text_error(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE.value,
                TriRpcStatus(
                    GRpcCode.UNIMPLEMENTED,
                    description=(
                        f"Content-Type {content_type} is not supported"
                        if content_type
                        else "Content-Type is missing from the request"
                    ),
                ),
            )
            return

        # check path
        path = headers.path
        if not path:
            self._response_plain_text_error(
                HttpStatus.NOT_FOUND.value,
                TriRpcStatus(
                    GRpcCode.UNIMPLEMENTED,
                    description="Expected path but is missing",
                ),
            )
            return
        elif not path.startswith("/"):
            self._response_plain_text_error(
                HttpStatus.NOT_FOUND.value,
                TriRpcStatus(
                    GRpcCode.UNIMPLEMENTED,
                    description=f"Expected path to start with /: {path}",
                ),
            )
            return

        # split the path
        parts = path.split("/")
        if len(parts) != 3:
            self._response_error(TriRpcStatus(GRpcCode.UNIMPLEMENTED, description=f"Bad path format: {path}"))
            return

        service_name, method_name = parts[1], parts[2]

        # get method handler
        handler = self._get_handler(service_name, method_name)
        if not handler:
            self._response_error(
                TriRpcStatus(
                    GRpcCode.UNIMPLEMENTED,
                    description=f"Service {service_name} is not found",
                )
            )
            return

        if end_stream:
            # Invalid request, ignore it.
            return

        decompressor: Decompressor = Identity()
        message_encoding = headers.get(TripleHeaderName.GRPC_ENCODING.value)
        if message_encoding and message_encoding != decompressor.get_message_encoding():
            # update decompressor
            try:
                decompressor = extensionLoader.get_extension(Decompressor, message_encoding)()
            except ExtensionError:
                self._response_error(
                    TriRpcStatus(
                        GRpcCode.UNIMPLEMENTED,
                        description=f"Grpc-encoding '{message_encoding}' is not supported",
                    )
                )
                return

        # create a server call
        self._listener = TripleServerCall(TripleServerStream(self._stream), handler, self._executor)

        # create a decoder
        self._decoder = TriDecoder(ServerTransportListener.ServerDecoderListener(self._listener), decompressor)

        # deliver the headers to the listener
        self._listener.on_headers(headers.to_dict())

    def _get_handler(self, service_name: str, method_name: str) -> Optional[RpcMethodHandler]:
        """
        Get the method handler.
        :param service_name: The service name
        :type service_name: str
        :param method_name: The method name
        :type method_name: str
        :return: The method handler
        :rtype: Optional[RpcMethodHandler]
        """
        if self._service_handles:
            service_handler = self._service_handles.get(service_name)
            if service_handler:
                return service_handler.method_handlers.get(method_name)
        return None

    def on_data(self, data: bytes, end_stream: bool) -> None:
        if self._decoder:
            self._decoder.decode(data)
            if end_stream:
                self._decoder.close()

    def cancel_by_remote(self, error_code: Http2ErrorCode) -> None:
        if self._listener:
            self._listener.on_cancel_by_remote(
                TriRpcStatus(
                    GRpcCode.CANCELLED,
                    description=f"Canceled by client ,errorCode= {error_code.value}",
                )
            )

    def _response_plain_text_error(self, code: int, status: TriRpcStatus) -> None:
        """
        Error before create server stream, http plain text will be returned.
        :param code: The error code
        :type code: int
        :param status: The status
        :type status: TriRpcStatus
        """
        # create headers
        headers = Http2Headers()
        headers.status = code
        headers.add(TripleHeaderName.GRPC_STATUS.value, status.code.value)
        headers.add(TripleHeaderName.GRPC_MESSAGE.value, status.description)
        headers.add(TripleHeaderName.CONTENT_TYPE.value, TripleHeaderValue.TEXT_PLAIN_UTF8.value)

        # send headers
        self._stream.send_headers(headers, end_stream=True)

    def _response_error(self, status: TriRpcStatus) -> None:
        """
        Error after create server stream, grpc error will be returned.
        :param status: The status
        :type status: TriRpcStatus
        """
        # create trailers
        trailers = Http2Headers()
        trailers.status = HttpStatus.OK.value
        trailers.add(TripleHeaderName.GRPC_STATUS.value, status.code.value)
        trailers.add(TripleHeaderName.GRPC_MESSAGE.value, status.description)
        trailers.add(
            TripleHeaderName.CONTENT_TYPE.value,
            TripleHeaderValue.APPLICATION_GRPC_PROTO.value,
        )

        # send trailers
        self._stream.send_headers(trailers, end_stream=True)

    class ServerDecoderListener(TriDecoder.Listener):
        """
        ServerDecoderListener is a callback interface that receives events on the decoder.
        """

        def __init__(self, listener: ServerStream.Listener):
            self._listener = listener

        def on_message(self, message: bytes) -> None:
            self._listener.on_message(message)

        def close(self):
            self._listener.on_complete()
