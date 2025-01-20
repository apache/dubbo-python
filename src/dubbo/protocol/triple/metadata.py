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

from dubbo.compression import Compressor, Identity
from dubbo.protocol.triple.constants import TripleHeaderName, TripleHeaderValue
from dubbo.remoting.aio.http2.headers import Http2Headers, HttpMethod


class RequestMetadata:
    """
    The request metadata.
    """

    def __init__(self):
        self.scheme: Optional[str] = None
        self.application: Optional[str] = None
        self.service: Optional[str] = None
        self.version: Optional[str] = None
        self.group: Optional[str] = None
        self.address: Optional[str] = None
        self.acceptEncoding: Optional[str] = None
        self.timeout: Optional[str] = None
        self.compressor: Compressor = Identity()
        self.method: Optional[str] = None
        self.attachments: dict[str, Any] = {}

    def to_headers(self) -> Http2Headers:
        """
        Convert to HTTP/2 headers.
        :return: The HTTP/2 headers.
        :rtype: Http2Headers
        """
        headers = Http2Headers()
        headers.scheme = self.scheme
        headers.authority = self.address
        headers.method = HttpMethod.POST.value
        headers.path = f"/{self.service}/{self.method}"
        headers.add(
            TripleHeaderName.CONTENT_TYPE.value,
            TripleHeaderValue.APPLICATION_GRPC_PROTO.value,
        )

        if self.version != "1.0.0":
            set_if_not_none(headers, TripleHeaderName.SERVICE_VERSION.value, self.version)

        set_if_not_none(headers, TripleHeaderName.GRPC_TIMEOUT.value, self.timeout)
        set_if_not_none(headers, TripleHeaderName.SERVICE_GROUP.value, self.group)
        set_if_not_none(headers, TripleHeaderName.CONSUMER_APP_NAME.value, self.application)
        set_if_not_none(headers, TripleHeaderName.GRPC_ENCODING.value, self.acceptEncoding)

        if self.compressor.get_message_encoding() != Identity.get_message_encoding():
            set_if_not_none(
                headers,
                TripleHeaderName.GRPC_ENCODING.value,
                self.compressor.get_message_encoding(),
            )

        [headers.add(k, str(v)) for k, v in self.attachments.items()]

        return headers


def set_if_not_none(headers: Http2Headers, key: str, value: Optional[str]) -> None:
    """
    Set the header if the value is not None.
    :param headers: The headers.
    :type headers: Http2Headers
    :param key: The key.
    :type key: str
    :param value: The value.
    :type value: Optional[str]
    """
    if value:
        headers.add(key, str(value))
