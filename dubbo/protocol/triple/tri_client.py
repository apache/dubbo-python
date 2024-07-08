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
import queue
from typing import Any, List, Optional, Tuple

from dubbo.compressor.compressor import Compressor, DeCompressor
from dubbo.constants import common_constants
from dubbo.constants.common_constants import CALL_CLIENT_STREAM, CALL_UNARY
from dubbo.constants.type_constants import (DeserializingFunction,
                                            SerializingFunction)
from dubbo.extension import extensionLoader
from dubbo.protocol.result import Result
from dubbo.protocol.triple.tri_codec import TriDecoder, TriEncoder
from dubbo.remoting.aio.h2_stream import Stream
from dubbo.url import URL


class TriClientCall(Stream.Listener):

    def __init__(
        self,
        listener: "TriClientCall.Listener",
        url: URL,
        request_serializer: Optional[SerializingFunction] = None,
        response_deserializer: Optional[DeserializingFunction] = None,
    ):
        self._stream: Optional[Stream] = None
        self._listener = listener

        # Try to get the compressor and decompressor from the URL
        self._compressor = self._decompressor = None
        if compressor_str := url.get_parameter(common_constants.COMPRESSOR_KEY):
            self._compressor = extensionLoader.get_extension(Compressor, compressor_str)
        if decompressor_str := url.get_parameter(common_constants.DECOMPRESSOR_KEY):
            self._decompressor = extensionLoader.get_extension(
                DeCompressor, decompressor_str
            )

        self._compressed = self._compressor is not None
        self._encoder = TriEncoder(self._compressor)
        self._request_serializer = request_serializer

        class TriDecoderListener(TriDecoder.Listener):

            def __init__(
                self,
                _listener: "TriClientCall.Listener",
                _response_deserializer: Optional[DeserializingFunction] = None,
            ):
                self._listener = _listener
                self._response_deserializer = _response_deserializer

            def on_message(self, message: bytes):
                if self._response_deserializer:
                    message = self._response_deserializer(message)
                self._listener.on_message(message)

            def close(self):
                self._listener.on_complete()

        self._response_deserializer = response_deserializer
        self._decoder = TriDecoder(
            TriDecoderListener(self._listener, self._response_deserializer),
            self._decompressor,
        )

        self._header_received = False
        self._headers = None
        self._trailers = None

    def bind_stream(self, stream: Stream) -> None:
        """
        Bind stream
        """
        self._stream = stream

    def send_headers(self, headers: List[Tuple[str, str]], last: bool = False) -> None:
        """
        Send headers
        Args:
            headers (List[Tuple[str, str]]): Headers
            last (bool): Last frame or not
        """
        self._stream.send_headers(headers, end_stream=last)

    def send_message(self, message: Any, last: bool = False) -> None:
        """
        Send a message
        Args:
            message (Any): Message to send
            last (bool): Last frame or not
        """
        if self._request_serializer:
            data = self._request_serializer(message)
        elif isinstance(message, bytes):
            data = message
        else:
            raise TypeError("Message must be bytes or serialized by req_serializer")

        # Encode data
        frame_payload = self._encoder.encode(data, self._compressed)
        # Send data frame
        self._stream.send_data(frame_payload, end_stream=last)

    def on_headers(self, headers: List[Tuple[str, str]]) -> None:
        if not self._header_received:
            self._headers = headers
            self._header_received = True
        else:
            # receive trailers
            self._trailers = headers

    def on_data(self, data: bytes) -> None:
        self._decoder.decode(data)

    def on_complete(self) -> None:
        self._decoder.close()

    def on_reset(self, err_code: int) -> None:
        # TODO: handle reset
        pass

    class Listener:

        def on_message(self, message: Any) -> None:
            """
            Callback when message is received
            """
            raise NotImplementedError("on_message() is not implemented")

        def on_complete(self) -> None:
            """
            Callback when the stream is complete
            """
            raise NotImplementedError("on_complete() is not implemented")


class TriResult(Result):
    """
    Triple result
    """

    END_SIGNAL = object()

    def __init__(self, call_type: str):
        self._call_type = call_type
        self._value_queue = queue.Queue()
        self._exception = None

    def set_value(self, value: Any) -> None:
        self._value_queue.put(value)
        if self._call_type in [CALL_UNARY, CALL_CLIENT_STREAM]:
            # Notify the caller that the value is ready
            self._value_queue.put(self.END_SIGNAL)

    def get_value(self) -> Any:
        if self._call_type in [CALL_UNARY, CALL_CLIENT_STREAM]:
            return self._get_single_value()
        else:
            return self._iterating_values()

    def _get_single_value(self) -> Any:
        value = self._value_queue.get()
        if value is self.END_SIGNAL:
            return None
        return value

    def _iterating_values(self) -> Any:
        while True:
            # block until the value is ready
            value = self._value_queue.get()
            if value is self.END_SIGNAL:
                # break the loop when the value is end signal
                break
            yield value

    def set_exception(self, exception: Exception) -> None:
        # close the value queue
        self._value_queue.put(None)
        self._exception = exception

    def get_exception(self) -> Exception:
        return self._exception
