#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Optional

from ._interface import DeserializationException, ProtobufDecoder, ProtobufEncoder, SerializationException

__all__ = ["ProtobufTransportCodec"]


class ProtobufTransportEncoder:
    """Protobuf encoder for parameters"""

    def __init__(self, handlers: list[ProtobufEncoder], parameter_types: Optional[list[type]] = None):
        self._handlers = handlers
        self._parameter_types = parameter_types or []

    def encode(self, arguments: tuple) -> bytes:
        """Encode arguments tuple to bytes"""
        try:
            if not arguments:
                return b""
            if len(arguments) == 1:
                return self._encode_single(arguments[0])
            raise SerializationException(
                f"Multiple parameters not supported. Got {len(arguments)} arguments, expected 1."
            )
        except Exception as e:
            raise SerializationException(f"Parameter encoding failed: {e}") from e

    def _encode_single(self, argument: Any) -> bytes:
        """Encode a single argument"""
        if argument is None:
            return b""

        # Try to get parameter type from configuration
        param_type = self._parameter_types[0] if self._parameter_types else None

        for handler in self._handlers:
            if handler.can_handle(argument, param_type):
                return handler.encode(argument, param_type)

        raise SerializationException(f"No handler found for {type(argument)}")


class ProtobufTransportDecoder:
    """Protobuf decoder for return values"""

    def __init__(self, handlers: list[ProtobufDecoder], return_type: Optional[type] = None):
        self._handlers = handlers
        self._return_type = return_type

    def decode(self, data: bytes) -> Any:
        """Decode bytes to return value"""
        try:
            if not data:
                return None
            if not self._return_type:
                raise DeserializationException("No return_type specified for decoding")

            for handler in self._handlers:
                if handler.can_handle(None, self._return_type):
                    return handler.decode(data, self._return_type)

            raise DeserializationException(f"No handler found for {self._return_type}")
        except Exception as e:
            raise DeserializationException(f"Return value decoding failed: {e}") from e


class ProtobufTransportCodec:
    """
    Main protobuf codec class
    """

    def __init__(
        self,
        parameter_types: Optional[list[type]] = None,
        return_type: Optional[type] = None,
        **kwargs,
    ):
        self._parameter_types = parameter_types or []
        self._return_type = return_type

        # Initialize handlers
        self._encoders: list[ProtobufEncoder] = []
        self._decoders: list[ProtobufDecoder] = []

        # Load default handlers
        self._load_default_handlers()

    def _load_default_handlers(self):
        """Load default encoding and decoding handlers"""
        from dubbo.extension import extensionLoader

        # Try BetterProto handler
        try:
            betterproto_handler = extensionLoader.get_extension(ProtobufEncoder, "betterproto")()
            self._encoders.append(betterproto_handler)
            self._decoders.append(betterproto_handler)
        except ImportError:
            print("Warning: BetterProto handler not available")

        # Try Google Protoc handler
        try:
            protoc_handler = extensionLoader.get_extension(ProtobufEncoder, "googleproto")()
            self._encoders.append(protoc_handler)
            self._decoders.append(protoc_handler)
        except ImportError:
            print("Warning: Protoc handler not available")

        # Always load primitive handler
        primitive_handler = extensionLoader.get_extension(ProtobufEncoder, "primitive")()
        self._encoders.append(primitive_handler)
        self._decoders.append(primitive_handler)

    def encoder(self) -> ProtobufTransportEncoder:
        """
        Create and return an encoder instance.
        """
        return ProtobufTransportEncoder(self._encoders, self._parameter_types)

    def decoder(self) -> ProtobufTransportDecoder:
        """
        Create and return a decoder instance.
        """
        return ProtobufTransportDecoder(self._decoders, self._return_type)

    # Convenience methods for direct usage (backward compatibility)
    def encode_parameter(self, argument: Any) -> bytes:
        """Encode a single parameter"""
        encoder = self.encoder()
        return encoder.encode((argument,))

    def encode_parameters(self, arguments: tuple) -> bytes:
        """Encode parameters tuple"""
        encoder = self.encoder()
        return encoder.encode(arguments)

    def decode_return_value(self, data: bytes) -> Any:
        """Decode return value"""
        decoder = self.decoder()
        return decoder.decode(data)

    def register_encoder(self, encoder: ProtobufEncoder):
        """Register a custom encoder"""
        self._encoders.append(encoder)

    def register_decoder(self, decoder: ProtobufDecoder):
        """Register a custom decoder"""
        self._decoders.append(decoder)

    def get_encoders(self) -> list[ProtobufEncoder]:
        """Get all registered encoders"""
        return self._encoders.copy()

    def get_decoders(self) -> list[ProtobufDecoder]:
        """Get all registered decoders"""
        return self._decoders.copy()
