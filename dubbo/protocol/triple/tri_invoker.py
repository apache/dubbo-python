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

from dubbo.compressor.compression import Compression
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.logger.logger_factory import loggerFactory
from dubbo.protocol.invocation import Invocation, RpcInvocation
from dubbo.protocol.invoker import Invoker
from dubbo.protocol.result import Result
from dubbo.protocol.triple.client.calls import TriClientCall
from dubbo.protocol.triple.client.stream_listener import TriClientStreamListener
from dubbo.protocol.triple.tri_constants import TripleHeaderName, TripleHeaderValue
from dubbo.protocol.triple.tri_results import TriResult
from dubbo.remoting.aio.http2.headers import Http2Headers, MethodType
from dubbo.remoting.aio.http2.stream_handler import StreamClientMultiplexHandler
from dubbo.remoting.transporter import Client
from dubbo.url import URL

logger = loggerFactory.get_logger(__name__)


class TriInvoker(Invoker):
    """
    Triple invoker.
    """

    def __init__(
        self, url: URL, client: Client, stream_multiplexer: StreamClientMultiplexHandler
    ):
        self._url = url
        self._client = client
        self._stream_multiplexer = stream_multiplexer

        self._compression: Optional[Compression] = None
        compression_type = url.get_parameter(common_constants.COMPRESSION)
        if compression_type:
            self._compression = extensionLoader.get_extension(
                Compression, compression_type
            )

        self._destroyed = False

    def invoke(self, invocation: RpcInvocation) -> Result:
        call_type = invocation.get_attribute(common_constants.CALL_KEY)
        result = TriResult(call_type)

        if not self._client.is_connected():
            # Reconnect the client
            self._client.reconnect()

        # Create a new TriClientCall
        tri_client_call = TriClientCall(
            result,
            serialization=invocation.get_attribute(common_constants.SERIALIZATION),
            compression=self._compression,
        )

        # Create a new stream
        stream = self._stream_multiplexer.create(
            TriClientStreamListener(tri_client_call.listener, self._compression)
        )
        tri_client_call.bind_stream(stream)

        if call_type in (
            common_constants.CALL_UNARY,
            common_constants.CALL_SERVER_STREAM,
        ):
            self._invoke_unary(tri_client_call, invocation)
        elif call_type in (
            common_constants.CALL_CLIENT_STREAM,
            common_constants.CALL_BIDI_STREAM,
        ):
            self._invoke_stream(tri_client_call, invocation)

        return result

    def _invoke_unary(self, call: TriClientCall, invocation: Invocation) -> None:
        call.send_headers(self._create_headers(invocation))
        call.send_message(invocation.get_argument(), last=True)

    def _invoke_stream(self, call: TriClientCall, invocation: Invocation) -> None:
        call.send_headers(self._create_headers(invocation))
        next_message = None
        for message in invocation.get_argument():
            if next_message is not None:
                call.send_message(next_message, last=False)
            next_message = message
        call.send_message(next_message, last=True)

    def _create_headers(self, invocation: Invocation) -> Http2Headers:

        headers = Http2Headers()
        headers.scheme = TripleHeaderValue.HTTP.value
        headers.method = MethodType.POST
        headers.authority = self._url.location
        # set path
        path = ""
        if invocation.get_service_name():
            path += f"/{invocation.get_service_name()}"
        path += f"/{invocation.get_method_name()}"
        headers.path = path

        # set content type
        headers.content_type = TripleHeaderValue.APPLICATION_GRPC_PROTO.value

        # set te
        headers.add(TripleHeaderName.TE.value, TripleHeaderValue.TRAILERS.value)

        return headers

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._client.is_connected()

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def destroy(self) -> None:
        self._client.close()
        self._client = None
        self._stream_multiplexer = None
        self._url = None
