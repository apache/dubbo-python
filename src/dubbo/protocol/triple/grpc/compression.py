# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""The compressions of gRPC messages, named by grpc-encoding."""

from dubbo.compression import Compressor, get_compressor
from dubbo.constants import COMPRESSOR_KEY
from dubbo.extension import extensions
from dubbo.url import URL

__all__ = ["Compressors"]

# The grpc-encoding of messages sent as they are.
_IDENTITY = b"identity"


class Compressors:
    """The installed compressors, made when first used with the URL of one server or client."""

    def __init__(self, url: URL) -> None:
        names = extensions.names(Compressor)
        self.accept_encoding = b",".join([_IDENTITY, *(name.encode("ascii") for name in names)])
        self._url = url
        self._names = frozenset(names)
        self._compressors: dict[bytes, Compressor] = {}

    def configured(self) -> tuple[bytes, Compressor | None]:
        """Return the grpc-encoding that the ``compressor`` parameter of the URL names, identity when absent, and its compressor.

        Raises:
            ValueError: The parameter names no installed compressor.
        """
        encoding = self._url.parameters.get(COMPRESSOR_KEY, _IDENTITY.decode()).encode("ascii")
        try:
            return encoding, self.get(encoding)
        except LookupError as error:
            raise ValueError(f"URL parameter {COMPRESSOR_KEY!r}: {error}") from None

    def get(self, encoding: bytes | None) -> Compressor | None:
        """Return the compressor of a grpc-encoding; ``None`` for identity.

        Raises:
            LookupError: No compressor is installed for ``encoding``.
        """
        if encoding is None or encoding == _IDENTITY:
            return None

        compressor = self._compressors.get(encoding)
        if compressor is None:
            name = encoding.decode("latin-1")
            if name not in self._names:
                raise LookupError(f"grpc-encoding {encoding!r} is not supported, only {self.accept_encoding.decode()}")
            compressor = self._compressors[encoding] = get_compressor(name, self._url)

        return compressor
