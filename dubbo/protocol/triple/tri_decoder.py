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
import enum

from dubbo.compressor.compressor import DeCompressor


class GrpcDecodeState(enum.Enum):
    """
    gRPC Decode State
    """

    HEADER = 0
    PAYLOAD = 1


class TriDecoder:
    """
    This class is responsible for decoding the gRPC message format, which is composed of a header and payload.
    gRPC Message Format Diagram

    +----------------------+-------------------------+------------------+
    | HTTP Header          | gRPC Header             | Business Data    |
    +----------------------+-------------------------+------------------+
    | (variable length)    | type (1 byte)           | data (variable)  |
    |                      | compressed-flag (1 byte)|                  |
    |                      | message length (4 byte) |                  |
    +----------------------+-------------------------+------------------+

    Args:
        decompressor (DeCompressor): The decompressor to use for decompressing the payload.
        listener (TriDecoder.Listener): The listener to deliver the decoded payload to.

    """

    HEADER_LENGTH: int = 5
    COMPRESSED_FLAG_MASK: int = 1
    RESERVED_MASK: int = 0xFE

    def __init__(self, decompressor: DeCompressor, listener: "TriDecoder.Listener"):
        self.accumulate = bytearray()
        self._decompressor = decompressor
        self._listener = listener
        self.state = GrpcDecodeState.HEADER
        self.required_length = self.HEADER_LENGTH
        self.compressed = False
        self.in_delivery = False
        self.closing = False
        self.closed = False

    def deframe(self, data: bytes):
        """
        Process the incoming bytes, deframing the gRPC message and delivering the payload to the listener.
        """
        self.accumulate.extend(data)
        self._deliver()

    def close(self):
        """
        Close the decoder and listener.
        """
        self.closing = True
        self._deliver()

    def _deliver(self):
        """
        Deliver the accumulated bytes to the listener, processing the header and payload as necessary.
        """
        if self.in_delivery:
            return

        self.in_delivery = True
        try:
            while self._has_enough_bytes():
                if self.state == GrpcDecodeState.HEADER:
                    self._process_header()
                elif self.state == GrpcDecodeState.PAYLOAD:
                    self._process_payload()
            if self.closing:
                if not self.closed:
                    self.closed = True
                    self.accumulate = None
                    self._listener.close()
        finally:
            self.in_delivery = False

    def _has_enough_bytes(self):
        """
        Check if the accumulated bytes are enough to process the header or payload
        """
        return len(self.accumulate) >= self.required_length

    def _process_header(self):
        """
        Processes the GRPC compression header which is composed of the compression flag and the outer frame length.
        """
        header_bytes = self.accumulate[: self.required_length]
        self.accumulate = self.accumulate[self.required_length :]

        type_byte = header_bytes[0]

        if type_byte & self.RESERVED_MASK:
            raise ValueError("gRPC frame header malformed: reserved bits not zero")

        self.compressed = bool(type_byte & self.COMPRESSED_FLAG_MASK)
        self.required_length = int.from_bytes(header_bytes[1:], byteorder="big")

        # Continue to process the payload
        self.state = GrpcDecodeState.PAYLOAD

    def _process_payload(self):
        """
        Processes the GRPC message body, which depending on frame header flags may be compressed.
        """
        payload_bytes = self.accumulate[: self.required_length]
        self.accumulate = self.accumulate[self.required_length :]

        if self.compressed:
            # Decompress the payload
            payload_bytes = self._decompressor.decompress(payload_bytes)

        self._listener.on_message(payload_bytes)

        # Done with this frame, begin processing the next header.
        self.required_length = self.HEADER_LENGTH
        self.state = GrpcDecodeState.HEADER

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
