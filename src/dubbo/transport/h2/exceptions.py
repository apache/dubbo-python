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

from dubbo.exceptions import DubboError

__all__ = [
    "H2ConnectionError",
    "H2Error",
    "H2StreamError",
    "H2StreamResetError",
]


class H2Error(DubboError):
    """A failure of the HTTP/2 transport."""


class H2ConnectionError(H2Error):
    """A failure to listen, to establish an HTTP/2 connection, or of the connection.

    Attributes:
        error_code: The received or generated HTTP/2 error code, if known.
        last_stream_id: The GOAWAY last-stream identifier, if received.
    """

    error_code: int | None
    last_stream_id: int | None

    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        last_stream_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.last_stream_id = last_stream_id


class H2StreamError(H2Error):
    """An invalid local use of one HTTP/2 stream, or a failure confined to it.

    This includes operation ordering, overlapping use in one direction, and
    stream-level protocol-engine failures.

    Attributes:
        stream_id: The connection-local stream identifier.
    """

    stream_id: int

    def __init__(self, message: str, *, stream_id: int) -> None:
        super().__init__(message)
        self.stream_id = stream_id


class H2StreamResetError(H2StreamError):
    """An RST_STREAM the peer sent on an HTTP/2 stream.

    Attributes:
        error_code: The peer's error code. Unknown extension codes are
            preserved as integers.
    """

    error_code: int

    def __init__(self, stream_id: int, error_code: int) -> None:
        super().__init__(
            f"the HTTP/2 stream {stream_id} was reset with error code {error_code}",
            stream_id=stream_id,
        )
        self.error_code = error_code
