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

from dubbo.compressor.compression import Compression
from dubbo.logger.logger_factory import loggerFactory
from dubbo.protocol.triple.client.calls import ClientCall
from dubbo.protocol.triple.tri_codec import TriDecoder
from dubbo.protocol.triple.tri_constants import TripleHeaderName, TripleHeaderValue
from dubbo.protocol.triple.tri_status import TriRpcCode, TriRpcStatus
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import Http2ErrorCode
from dubbo.remoting.aio.http2.stream import StreamListener

logger = loggerFactory.get_logger(__name__)


class _TriDecoderListener(TriDecoder.Listener):
    """
    Triple decoder listener.
    """

    def __init__(self, listener: ClientCall.Listener):
        self._listener = listener
        self._rpc_status = None
        self._trailers = None

    def add_rpc_status(self, status: TriRpcStatus):
        self._rpc_status = status

    def add_trailers(self, trailers: list):
        self._trailers = trailers

    def on_message(self, message: Any) -> None:
        self._listener.on_message(message)

    def close(self):
        self._listener.on_close(self._rpc_status, self._trailers)


class TriClientStreamListener(StreamListener):
    """
    Stream listener for triple client.
    """

    def __init__(
        self, listener: ClientCall.Listener, compression: Optional[Compression] = None
    ):
        super().__init__()
        self._tri_decoder_listener = _TriDecoderListener(listener)
        self._tri_decoder = TriDecoder(self._tri_decoder_listener, compression)

    def on_headers(self, headers: Http2Headers, end_stream: bool) -> None:
        # validate headers
        validated = True
        if headers.status != "200":
            # Illegal response code
            validated = False
            logger.error(f"Invalid response code: {headers.status}")
        if content_type := headers.get(TripleHeaderName.CONTENT_TYPE.value):
            # Invalid content type
            if not content_type.startswith(TripleHeaderValue.APPLICATION_GRPC.value):
                validated = False
                logger.error(
                    f"Invalid content type: {headers.get(TripleHeaderName.CONTENT_TYPE.value)}"
                )
        else:
            # Missing content type
            validated = False
            logger.error("Missing content type")

        if not validated:
            # TODO channel by local
            pass

    def on_data(self, data: bytes, end_stream: bool) -> None:
        # Decode the data
        self._tri_decoder.decode(data)
        if end_stream:
            self._tri_decoder.close()

    def on_trailers(self, headers: Http2Headers) -> None:
        tri_status = TriRpcStatus(
            TriRpcCode.from_code(int(headers.get(TripleHeaderName.GRPC_STATUS.value))),
            description=headers.get(TripleHeaderName.GRPC_MESSAGE.value),
        )
        trailers = headers.to_list()

        self._tri_decoder_listener.add_rpc_status(tri_status)
        self._tri_decoder_listener.add_trailers(trailers)

        self._tri_decoder.close()

    def on_reset(self, error_code: Http2ErrorCode) -> None:
        pass
