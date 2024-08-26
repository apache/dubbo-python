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

from dubbo.compression import Compressor, Identity
from dubbo.constants import common_constants
from dubbo.extension import ExtensionError, extensionLoader
from dubbo.loggers import loggerFactory
from dubbo.protocol import Invoker, Result
from dubbo.protocol.invocation import Invocation, RpcInvocation
from dubbo.protocol.triple.call import TripleClientCall
from dubbo.protocol.triple.call.client_call import DefaultClientCallListener
from dubbo.protocol.triple.constants import TripleHeaderName, TripleHeaderValue
from dubbo.protocol.triple.metadata import RequestMetadata
from dubbo.protocol.triple.results import TriResult
from dubbo.remoting import Client
from dubbo.remoting.aio.exceptions import RemotingError
from dubbo.remoting.aio.http2.stream_handler import StreamClientMultiplexHandler
from dubbo.serialization import (
    CustomDeserializer,
    CustomSerializer,
    DirectDeserializer,
    DirectSerializer,
)
from dubbo.types import CallType
from dubbo.url import URL

__all__ = ["TripleInvoker"]

_LOGGER = loggerFactory.get_logger()


class TripleInvoker(Invoker):
    """
    Triple invoker.
    """

    __slots__ = ["_url", "_client", "_stream_multiplexer", "_compression"]

    def __init__(
        self, url: URL, client: Client, stream_multiplexer: StreamClientMultiplexHandler
    ):
        self._url = url
        self._client = client
        self._stream_multiplexer = stream_multiplexer

    def invoke(self, invocation: RpcInvocation) -> Result:
        call_type: CallType = invocation.get_attribute(common_constants.CALL_KEY)
        result = TriResult(call_type)

        if not self._client.is_connected():
            result.set_exception(
                RemotingError("The client is not connected to the server.")
            )
            return result

        # get serializer
        serializer = DirectSerializer()
        serializing_function = invocation.get_attribute(common_constants.SERIALIZER_KEY)
        if serializing_function:
            serializer = CustomSerializer(serializing_function)

        # get deserializer
        deserializer = DirectDeserializer()
        deserializing_function = invocation.get_attribute(
            common_constants.DESERIALIZER_KEY
        )
        if deserializing_function:
            deserializer = CustomDeserializer(deserializing_function)

        # Create a new TriClientCall
        tri_client_call = TripleClientCall(
            self._stream_multiplexer,
            DefaultClientCallListener(result),
            serializer,
            deserializer,
        )

        # start the call
        try:
            metadata = self._create_metadata(invocation)
            tri_client_call.start(metadata)
        except ExtensionError as e:
            result.set_exception(e)
            return result

        # invoke
        if not call_type.client_stream:
            self._invoke_unary(tri_client_call, invocation)
        else:
            self._invoke_stream(tri_client_call, invocation)

        return result

    def _invoke_unary(self, call: TripleClientCall, invocation: Invocation) -> None:
        """
        Invoke a unary call.
        :param call: The call to invoke.
        :type call: TripleClientCall
        :param invocation: The invocation to invoke.
        :type invocation: Invocation
        """
        try:
            argument = invocation.get_argument()
            if callable(argument):
                argument = argument()
        except Exception as e:
            _LOGGER.exception(f"Invoke failed: {str(e)}", e)
            call.cancel_by_local(e)
            return

        # send the message
        call.send_message(argument, last=True)

    def _invoke_stream(self, call: TripleClientCall, invocation: Invocation) -> None:
        """
        Invoke a stream call.
        :param call: The call to invoke.
        :type call: TripleClientCall
        :param invocation: The invocation to invoke.
        :type invocation: Invocation
        """
        try:
            # get the argument
            argument = invocation.get_argument()
            iterator = argument() if callable(argument) else argument

            # send the messages
            BEGIN_SIGNAL = object()
            next_message = BEGIN_SIGNAL
            for message in iterator:
                if next_message is not BEGIN_SIGNAL:
                    call.send_message(next_message, last=False)
                next_message = message
            next_message = next_message if next_message is not BEGIN_SIGNAL else None
            call.send_message(next_message, last=True)
        except Exception as e:
            _LOGGER.exception(f"Invoke failed: {str(e)}", e)
            call.cancel_by_local(e)

    def _create_metadata(self, invocation: Invocation) -> RequestMetadata:
        """
        Create the metadata.
        :param invocation: The invocation.
        :type invocation: Invocation
        :return: The metadata.
        :rtype: RequestMetadata
        :raise ExtensionError: If the compressor is not supported.
        """
        metadata = RequestMetadata()
        # set service and method
        metadata.service = invocation.get_service_name()
        metadata.method = invocation.get_method_name()

        # get scheme
        metadata.scheme = (
            TripleHeaderValue.HTTPS.value
            if self._url.parameters.get(common_constants.SSL_ENABLED_KEY, False)
            else TripleHeaderValue.HTTP.value
        )

        # get compressor
        compression = self._url.parameters.get(
            common_constants.COMPRESSION_KEY, Identity.get_message_encoding()
        )
        if metadata.compressor.get_message_encoding() != compression:
            try:
                metadata.compressor = extensionLoader.get_extension(
                    Compressor, compression
                )()
            except ExtensionError as e:
                _LOGGER.error(f"Unsupported compression: {compression}")
                raise e

        # get address
        metadata.address = self._url.location

        # TODO add more metadata
        metadata.attachments[TripleHeaderName.TE.value] = (
            TripleHeaderValue.TRAILERS.value
        )

        return metadata

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._client.is_connected()

    def destroy(self) -> None:
        self._client.close()
        self._client = None
        self._stream_multiplexer = None
        self._url = None
