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
import struct
from typing import Optional

from dubbo.compressor.compression import Compression

"""
    gRPC Message Format Diagram
    +----------------------+-------------------------+------------------+
    | HTTP Header          | gRPC Header             | Business Data    |
    +----------------------+-------------------------+------------------+
    | (variable length)    | compressed-flag (1 byte)| data (variable)  |
    |                      | message length (4 byte) |                  |
    +----------------------+-------------------------+------------------+
"""

HEADER: str = "HEADER"
PAYLOAD: str = "PAYLOAD"

# About HEADER
HEADER_LENGTH: int = 5
COMPRESSED_FLAG_MASK: int = 1
RESERVED_MASK = 0xFE


class TriEncoder:
    """
    This class is responsible for encoding the gRPC message format, which is composed of a header and payload.

    Args:
        compression (Optional[Compression]): The Compression to use for compressing or decompressing the payload.
    """

    HEADER_LENGTH: int = 5
    COMPRESSED_FLAG_MASK: int = 1

    def __init__(self, compression: Optional[Compression]):
        self._compression = compression

    def encode(self, message: bytes) -> bytes:
        """
        Encode the message into the gRPC message format.

        Args:
            message (bytes): The message to encode.
        Returns:
            bytes: The encoded message in gRPC format.
        """
        compressed_flag = COMPRESSED_FLAG_MASK if self._compression else 0
        if self._compression:
            # Compress the payload
            message = self._compression.compress(message)

        message_length = len(message)
        if message_length > 0xFFFFFFFF:
            raise ValueError("Message too large to encode")

        # Create the header
        header = struct.pack(">BI", compressed_flag, message_length)

        return header + message


class TriDecoder:
    """
    This class is responsible for decoding the gRPC message format, which is composed of a header and payload.

    Args:
        listener (TriDecoder.Listener): The listener to deliver the decoded payload to.
        compression (Optional[Compression]): The Compression to use for compressing or decompressing the payload.
    """

    def __init__(
        self,
        listener: "TriDecoder.Listener",
        compression: Optional[Compression],
    ):
        # store data for decoding
        self._accumulate = bytearray()
        self._listener = listener
        self._compression = compression

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
        """
        return len(self._accumulate) >= self._required_length

    def _process_header(self) -> None:
        """
        Processes the GRPC compression header which is composed of the compression flag and the outer frame length.
        """
        header_bytes = self._accumulate[: self._required_length]
        self._accumulate = self._accumulate[self._required_length :]
        # Parse the header
        compressed_flag = header_bytes[0]
        if (compressed_flag & RESERVED_MASK) != 0:
            raise ValueError("gRPC frame header malformed: reserved bits not zero")

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
            payload_bytes = self._compression.decompress(payload_bytes)

        self._listener.on_message(bytes(payload_bytes))

        # Done with this frame, begin processing the next header.
        self._required_length = HEADER_LENGTH
        self._state = HEADER

    class Listener:
        def on_message(self, message: bytes):
            """
            Called when a message is received.
            """
            raise NotImplementedError("Listener.on_message() not implemented")

        def close(self):
            """
            Called when the listener is closed.
            """
            raise NotImplementedError("Listener.close() not implemented")
