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
from typing import Any, List, Tuple

from dubbo.constants import common_constants
from dubbo.logger.logger_factory import loggerFactory
from dubbo.protocol.invocation import Invocation, RpcInvocation
from dubbo.protocol.invoker import Invoker
from dubbo.protocol.result import Result
from dubbo.protocol.triple.tri_client import TriClientCall, TriResult
from dubbo.remoting.aio.h2_stream_handler import StreamHandler
from dubbo.remoting.transporter import Client
from dubbo.url import URL

logger = loggerFactory.get_logger(__name__)


class TriClientCallListener(TriClientCall.Listener):

    def __init__(self, result: TriResult):
        self._result = result

    def on_message(self, message: Any) -> None:
        # Set the message to the result
        self._result.set_value(message)

    def on_complete(self) -> None:
        # Set the end signal to the result
        self._result.set_value(self._result.END_SIGNAL)


class TriInvoker(Invoker):

    def __init__(self, url: URL, client: Client, stream_handler: StreamHandler):
        self._url = url
        self._client = client
        self._stream_handler = stream_handler

        self._destroyed = False

    def invoke(self, invocation: RpcInvocation) -> Result:
        call_type = invocation.get_attribute(common_constants.CALL_KEY)
        result = TriResult(call_type)

        # TODO Return an exception result
        if self.destroyed:
            logger.warning("The invoker has been destroyed.")
            raise Exception("The invoker has been destroyed.")
        elif not self._client.connected:
            pass

        # Create a new TriClientCall object
        tri_client_call = TriClientCall(
            TriClientCallListener(result),
            url=self._url,
            request_serializer=invocation.get_attribute(common_constants.SERIALIZATION),
            response_deserializer=invocation.get_attribute(
                common_constants.DESERIALIZATION
            ),
        )
        stream = self._stream_handler.create(tri_client_call)
        tri_client_call.bind_stream(stream)

        if call_type in (
            common_constants.CALL_UNARY,
            common_constants.CALL_SERVER_STREAM,
        ):
            self._invoke_unary(tri_client_call, invocation)
        elif call_type in (
            common_constants.CALL_CLIENT_STREAM,
            common_constants.CALL_BIDI_STREAM,
        ):
            self._invoke_stream(tri_client_call, invocation)

        return result

    def _invoke_unary(self, call: TriClientCall, invocation: Invocation) -> None:
        call.send_headers(self._create_headers(invocation))
        call.send_message(invocation.get_argument(), last=True)

    def _invoke_stream(self, call: TriClientCall, invocation: Invocation) -> None:
        call.send_headers(self._create_headers(invocation))
        next_message = None
        for message in invocation.get_argument():
            if next_message is not None:
                call.send_message(next_message, last=False)
            next_message = message
        call.send_message(next_message, last=True)

    def _create_headers(self, invocation: Invocation) -> List[Tuple[str, str]]:

        headers = [
            (":method", "POST"),
            (":authority", self._url.location),
            (":scheme", self._url.scheme),
            (
                ":path",
                f"/{invocation.get_service_name()}/{invocation.get_method_name()}",
            ),
            ("content-type", "application/grpc+proto"),
            ("te", "trailers"),
        ]
        # TODO Add more headers information
        return headers

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._client.connected

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def destroy(self) -> None:
        self._client.close()
        self._client = None
        self._stream_handler = None
        self._url = None
