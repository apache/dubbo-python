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

import abc
import struct
from typing import Optional

from dubbo.compression import Compressor, Decompressor
from dubbo.protocol.triple.exceptions import RpcError

"""
    gRPC Message Format Diagram (HTTP/2 Data Frame):
    +----------------------+-------------------------+------------------+
    | HTTP Header          | gRPC Header             | Business Data    |
    +----------------------+-------------------------+------------------+
    | (variable length)    | compressed-flag (1 byte)| data (variable)  |
    |                      | message length (4 byte) |                  |
    +----------------------+-------------------------+------------------+
"""

__all__ = ["TriEncoder", "TriDecoder"]

HEADER: str = "HEADER"
PAYLOAD: str = "PAYLOAD"

# About HEADER
HEADER_LENGTH: int = 5
COMPRESSED_FLAG_MASK: int = 1
RESERVED_MASK = 0xFE
DEFAULT_MAX_MESSAGE_SIZE: int = 4194304  # 4MB


class TriEncoder:
    """
    This class is responsible for encoding the gRPC message format, which is composed of a header and payload.
    """

    __slots__ = ["_compressor"]

    def __init__(self, compressor: Optional[Compressor]):
        """
        Initialize the encoder.
        :param compressor: The compression to use for compressing the payload.
        :type compressor: Optional[Compressor]
        """
        self._compressor = compressor

    @property
    def compressor(self) -> Optional[Compressor]:
        """
        Get the compressor.
        :return: The compressor.
        :rtype: Optional[Compressor]
        """
        return self._compressor

    @compressor.setter
    def compressor(self, value: Compressor) -> None:
        """
        Set the compressor.
        :param value: The compressor.
        :type value: Compressor
        """
        self._compressor = value

    def encode(self, message: bytes, compress_flag: int) -> bytes:
        """
        Encode the message into the gRPC message format.

        :param message: The message to encode.
        :type message: bytes
        :param compress_flag: The compress flag. 0 for no compression, 1 for compression.
        :type compress_flag: int
        :return: The encoded message.
        :rtype: bytes
        """

        # check compress_flag
        if compress_flag not in [0, 1]:
            raise RpcError(f"compress_flag must be 0 or 1, but got {compress_flag}")

        # check message size
        if len(message) > DEFAULT_MAX_MESSAGE_SIZE:
            raise RpcError(
                f"Message too large. Allowed maximum size is 4194304 bytes, but got {len(message)} bytes."
            )

        # check compress_flag and compress the payload
        if compress_flag == 1:
            if not self._compressor:
                raise RpcError("compression is required when compress_flag is 1")
            message = self._compressor.compress(message)

        # Create the gRPC header
        # >: big-endian
        # B: unsigned char(1 byte) -> compressed_flag
        # I: unsigned int(4 bytes) -> message_length
        header = struct.pack(">BI", compress_flag, len(message))

        return header + message


class TriDecoder:
    """
    This class is responsible for decoding the gRPC message format, which is composed of a header and payload.
    """

    __slots__ = [
        "_accumulate",
        "_listener",
        "_decompressor",
        "_state",
        "_required_length",
        "_decoding",
        "_compressed",
        "_closing",
        "_closed",
    ]

    def __init__(
        self,
        listener: "TriDecoder.Listener",
        decompressor: Optional[Decompressor],
    ):
        """
        Initialize the decoder.
        :param decompressor: The decompressor to use for decompressing the payload.
        :type decompressor: Optional[Decompressor]
        :param listener: The listener to deliver the decoded payload to when a message is received.
        :type listener: TriDecoder.Listener
        """

        self._listener = listener
        # store data for decoding
        self._accumulate = bytearray()
        self._decompressor = decompressor

        self._state = HEADER
        self._required_length = HEADER_LENGTH

        # decode state, if True, the decoder is currently processing a message
        self._decoding = False

        # whether the message is compressed
        self._compressed = False

        self._closing = False
        self._closed = False

    def decode(self, data: bytes) -> None:
        """
        Process the incoming bytes, decoding the gRPC message and delivering the payload to the listener.
        :param data: The data to decode.
        :type data: bytes
        """
        self._accumulate.extend(data)
        self._do_decode()

    def close(self) -> None:
        """
        Close the decoder and listener.
        """
        self._closing = True
        self._do_decode()

    def _do_decode(self) -> None:
        """
        Deliver the accumulated bytes to the listener, processing the header and payload as necessary.
        """
        if self._decoding:
            return

        self._decoding = True
        try:
            while self._has_enough_bytes():
                if self._state == HEADER:
                    self._process_header()
                elif self._state == PAYLOAD:
                    self._process_payload()
            if self._closing:
                if not self._closed:
                    self._closed = True
                    self._accumulate = None
                    self._listener.close()
        finally:
            self._decoding = False

    def _has_enough_bytes(self) -> bool:
        """
        Check if the accumulated bytes are enough to process the header or payload
        :return: True if there are enough bytes, False otherwise.
        :rtype: bool
        """
        return len(self._accumulate) >= self._required_length

    def _process_header(self) -> None:
        """
        Processes the GRPC compression header which is composed of the compression flag and the outer frame length.
        """
        header_bytes = self._accumulate[: self._required_length]
        self._accumulate = self._accumulate[self._required_length :]

        # Parse the header
        compressed_flag = int(header_bytes[0])
        if (compressed_flag & RESERVED_MASK) != 0:
            raise RpcError("gRPC frame header malformed: reserved bits not zero")
        else:
            self._compressed = bool(compressed_flag & COMPRESSED_FLAG_MASK)
            self._required_length = int.from_bytes(header_bytes[1:], byteorder="big")
            # Continue to process the payload
            self._state = PAYLOAD

    def _process_payload(self) -> None:
        """
        Processes the GRPC message body, which depending on frame header flags may be compressed.
        """
        payload_bytes = self._accumulate[: self._required_length]
        self._accumulate = self._accumulate[self._required_length :]

        if self._compressed:
            # Decompress the payload
            payload_bytes = self._decompressor.decompress(payload_bytes)

        self._listener.on_message(bytes(payload_bytes))

        # Done with this frame, begin processing the next header.
        self._required_length = HEADER_LENGTH
        self._state = HEADER

    class Listener(abc.ABC):
        @abc.abstractmethod
        def on_message(self, message: bytes):
            """
            Called when a message is received.
            :param message: The message received.
            :type message: bytes
            """
            raise NotImplementedError()

        @abc.abstractmethod
        def close(self):
            """
            Called when the listener is closed.
            """
            raise NotImplementedError()
