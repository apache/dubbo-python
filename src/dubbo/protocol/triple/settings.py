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

"""What a Triple server or invoker reads from its URL once, for every call it serves or makes."""

from typing import Self

import attrs

from dubbo.compression import Compressor
from dubbo.constants import DEFAULT_MAX_RECEIVE_MESSAGE_SIZE, MAX_RECEIVE_MESSAGE_SIZE_KEY, SHUTWAIT_KEY, TRIPLE_KEY
from dubbo.transport.tls import TLS_KEYS
from dubbo.url import URL

from .grpc.compression import Compressors

__all__ = ["TripleSettings", "transport_url"]

_PREFIX = f"{TRIPLE_KEY}."
# The parameters besides the Triple settings that the HTTP/2 server or client reads.
_TRANSPORT_KEYS = frozenset({*TLS_KEYS, SHUTWAIT_KEY})


def transport_url(url: URL) -> URL:
    """Return the URL of the server or connection that ``url`` is served or called over.

    It keeps the protocol, address and attributes of ``url``, the TLS
    parameters and ``shutwait``, and the Triple settings, the parameters
    after ``triple.``, without the prefix: those the protocol reads, such as
    ``compressor``, ``health-enabled`` and ``client``, and those of the
    HTTP/2 implementation, such as ``max-concurrent-streams``.
    """
    parameters = url.parameters
    kept = {key: value for key, value in parameters.items() if key in _TRANSPORT_KEYS}
    kept |= {key.removeprefix(_PREFIX): value for key, value in parameters.items() if key.startswith(_PREFIX)}
    return URL(protocol=url.protocol, host=url.host, port=url.port, parameters=kept, attributes=url.attributes)


@attrs.define(frozen=True, kw_only=True)
class TripleSettings:
    """The message limits and compression of a Triple server or invoker.

    Attributes:
        max_message_size: Bytes of the largest message received, which
            ``max-receive-message-size`` sets, 4 MiB when absent.
        compressors: The compressors a peer's encoding may name.
        encoding: The encoding the ``compressor`` parameter names, identity
            when absent.
        compressor: The compressor of that encoding; ``None`` for identity.
    """

    max_message_size: int
    compressors: Compressors
    encoding: bytes
    compressor: Compressor | None

    @classmethod
    def from_url(cls, url: URL) -> Self:
        """Read the settings of ``url``.

        Raises:
            ValueError: A parameter is invalid, or names no installed compressor.
        """
        size = url.get_parameter(MAX_RECEIVE_MESSAGE_SIZE_KEY, int, DEFAULT_MAX_RECEIVE_MESSAGE_SIZE)
        if size <= 0:
            raise ValueError(f"URL parameter {MAX_RECEIVE_MESSAGE_SIZE_KEY!r} must be positive")

        compressors = Compressors(url)
        encoding, compressor = compressors.configured()
        return cls(max_message_size=size, compressors=compressors, encoding=encoding, compressor=compressor)
