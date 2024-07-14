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
from typing import Optional


class Http2FrameType(enum.Enum):
    """
    Frame types are used in the frame header to identify the type of the frame.
    See: https://datatracker.ietf.org/doc/html/rfc7540#section-11.2
    """

    # Data frame, carries HTTP message bodies.
    DATA = 0x0

    # Headers frame, carries HTTP headers.
    HEADERS = 0x1

    # Priority frame, specifies the priority of a stream.
    PRIORITY = 0x2

    # Reset Stream frame, cancels a stream.
    RST_STREAM = 0x3

    # Settings frame, exchanges configuration parameters.
    SETTINGS = 0x4

    # Push Promise frame, used by the server to push resources.
    PUSH_PROMISE = 0x5

    # Ping frame, measures round-trip time and checks connectivity.
    PING = 0x6

    # Goaway frame, signals that the connection will be closed.
    GOAWAY = 0x7

    # Window Update frame, manages flow control window size.
    WINDOW_UPDATE = 0x8

    # Continuation frame, transmits large header blocks.
    CONTINUATION = 0x9


class Http2ErrorCode(enum.Enum):
    """
    Error codes are 32-bit fields that are used in RST_STREAM and GOAWAY frames to convey the reasons for the stream or connection error.

    see: https://datatracker.ietf.org/doc/html/rfc7540#section-11.4
    """

    # The associated condition is not a result of an error.
    NO_ERROR = 0x0

    # The endpoint detected an unspecific protocol error.
    PROTOCOL_ERROR = 0x1

    # The endpoint encountered an unexpected internal error.
    INTERNAL_ERROR = 0x2

    # The endpoint detected that its peer violated the flow-control protocol.
    FLOW_CONTROL_ERROR = 0x3

    # The endpoint sent a SETTINGS frame but did not receive a response in a timely manner.
    SETTINGS_TIMEOUT = 0x4

    # The endpoint received a frame after a stream was half-closed.
    STREAM_CLOSED = 0x5

    # The endpoint received a frame with an invalid size.
    FRAME_SIZE_ERROR = 0x6

    # The endpoint refused the stream prior to performing any application processing
    REFUSED_STREAM = 0x7

    # Used by the endpoint to indicate that the stream is no longer needed.
    CANCEL = 0x8

    # The endpoint is unable to maintain the header compression context for the connection.
    COMPRESSION_ERROR = 0x9

    # The connection established in response to a CONNECT request (Section 8.3) was reset or abnormally closed.
    CONNECT_ERROR = 0xA

    # The endpoint detected that its peer is exhibiting a behavior that might be generating excessive load.
    ENHANCE_YOUR_CALM = 0xB

    # The underlying transport has properties that do not meet minimum security requirements (see Section 9.2).
    INADEQUATE_SECURITY = 0xC

    # The endpoint requires that HTTP/1.1 be used instead of HTTP/2.
    HTTP_1_1_REQUIRED = 0xD

    @classmethod
    def get(cls, code: int):
        """
        Get the error code by code.
        Args:
            code: The error code.
        Returns:
            The error code.
        """
        for error_code in cls:
            if error_code.value == code:
                return error_code
        # Unknown or unsupported error codes MUST NOT trigger any special behavior.
        # These MAY be treated as equivalent to INTERNAL_ERROR.
        return cls.INTERNAL_ERROR


class Http2Settings:
    """
    The settings are used to communicate configuration parameters that affect how endpoints communicate.
    See: https://datatracker.ietf.org/doc/html/rfc7540#section-11.3
    """

    class Http2Setting:
        """
        HTTP/2 setting.
        """

        def __init__(self, code: int, initial_value: Optional[int] = None):
            self.code = code
            # If the initial value is "none", it means no limitation.
            self.initial_value = initial_value

    # Allows the sender to inform the remote endpoint of the maximum size of the header compression table used to decode header blocks, in octets.
    HEADER_TABLE_SIZE = Http2Setting(0x1, 4096)

    # This setting can be used to disable server push (Section 8.2).
    ENABLE_PUSH = Http2Setting(0x2, 1)

    # Indicates the maximum number of concurrent streams that the sender will allow.
    MAX_CONCURRENT_STREAMS = Http2Setting(0x3, None)

    # Indicates the sender's initial window size (in octets) for stream-level flow control.
    # This setting affects the window size of all streams
    INITIAL_WINDOW_SIZE = Http2Setting(0x4, 65535)

    # Indicates the size of the largest frame payload that the sender is willing to receive, in octets.
    MAX_FRAME_SIZE = Http2Setting(0x5, 16384)

    # This advisory setting informs a peer of the maximum size of header list that the sender is prepared to accept, in octets.
    MAX_HEADER_LIST_SIZE = Http2Setting(0x6, None)


class HttpStatus(enum.Enum):
    """
    Enum for HTTP status codes as defined in RFC 7231 and related specifications.
    """

    # 1xx Informational
    CONTINUE = 100
    SWITCHING_PROTOCOLS = 101

    # 2xx Success
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NON_AUTHORITATIVE_INFORMATION = 203
    NO_CONTENT = 204
    RESET_CONTENT = 205
    PARTIAL_CONTENT = 206

    # 3xx Redirection
    MULTIPLE_CHOICES = 300
    MOVED_PERMANENTLY = 301
    FOUND = 302
    SEE_OTHER = 303
    NOT_MODIFIED = 304
    USE_PROXY = 305
    TEMPORARY_REDIRECT = 307
    PERMANENT_REDIRECT = 308

    # 4xx Client Error
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    PAYMENT_REQUIRED = 402
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    NOT_ACCEPTABLE = 406
    PROXY_AUTHENTICATION_REQUIRED = 407
    REQUEST_TIMEOUT = 408
    CONFLICT = 409
    GONE = 410
    LENGTH_REQUIRED = 411
    PRECONDITION_FAILED = 412
    PAYLOAD_TOO_LARGE = 413
    URI_TOO_LONG = 414
    UNSUPPORTED_MEDIA_TYPE = 415
    RANGE_NOT_SATISFIABLE = 416
    EXPECTATION_FAILED = 417
    I_AM_A_TEAPOT = 418
    MISDIRECTED_REQUEST = 421
    UNPROCESSABLE_ENTITY = 422
    LOCKED = 423
    FAILED_DEPENDENCY = 424
    UPGRADE_REQUIRED = 426
    PRECONDITION_REQUIRED = 428
    TOO_MANY_REQUESTS = 429
    REQUEST_HEADER_FIELDS_TOO_LARGE = 431
    UNAVAILABLE_FOR_LEGAL_REASONS = 451

    # 5xx Server Error
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504
    HTTP_VERSION_NOT_SUPPORTED = 505
    VARIANT_ALSO_NEGOTIATES = 506
    INSUFFICIENT_STORAGE = 507
    LOOP_DETECTED = 508
    NOT_EXTENDED = 510
    NETWORK_AUTHENTICATION_REQUIRED = 511

    @classmethod
    def from_code(cls, code: int) -> "HttpStatus":
        for status in cls:
            if status.value == code:
                return status

    @staticmethod
    def is_1xx(status):
        """
        Check if the given status is an informational (1xx) status code.
        Args:
            status: HttpStatus to check
        Returns:
            True if the status code is in the 1xx range, False otherwise
        """
        return 100 <= status.value < 200

    @staticmethod
    def is_2xx(status):
        """
        Check if the given status is a successful (2xx) status code.
        Args:
            status: HttpStatus to check
        Returns:
            True if the status code is in the 2xx range, False otherwise
        """
        return 200 <= status.value < 300

    @staticmethod
    def is_3xx(status):
        """
        Check if the given status is a redirection (3xx) status code.
        Args:
            status: HttpStatus to check
        Returns:
            True if the status code is in the 3xx range, False otherwise
        """
        return 300 <= status.value < 400

    @staticmethod
    def is_4xx(status):
        """
        Check if the given status is a client error (4xx) status code.
        Args:
            status: HttpStatus to check
        Returns:
            True if the status code is in the 4xx range, False otherwise
        """
        return 400 <= status.value < 500

    @staticmethod
    def is_5xx(status):
        """
        Check if the given status is a server error (5xx) status code.
        Args:
            status: HttpStatus to check
        Returns:
            True if the status code is in the 5xx range, False otherwise
        """
        return 500 <= status.value < 600
