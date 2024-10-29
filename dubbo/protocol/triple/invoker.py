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
import concurrent
from collections.abc import Iterator

from dubbo.classes import MethodDescriptor
from dubbo.compression import Compressor, Identity
from dubbo.constants import common_constants
from dubbo.extension import ExtensionError, extensionLoader
from dubbo.loggers import loggerFactory
from dubbo.protocol import Invoker, Result
from dubbo.protocol.invocation import Invocation, RpcInvocation
from dubbo.protocol.triple.call import TripleClientCall
from dubbo.protocol.triple.call.client_call import (
    ReadStreamToClientCallListenerAdapter,
    FutureToClientCallListenerAdapter,
)
from dubbo.protocol.triple.constants import TripleHeaderName, TripleHeaderValue
from dubbo.protocol.triple.metadata import RequestMetadata
from dubbo.protocol.triple.results import TriResult
from dubbo.protocol.triple.streams import (
    TriReadWriteStream,
    TriClientWriteStream,
    TriReadStream,
)
from dubbo.remoting import Client
from dubbo.remoting.aio.exceptions import RemotingError
from dubbo.remoting.aio.http2.stream_handler import StreamClientMultiplexHandler
from dubbo.serialization import (
    CustomDeserializer,
    CustomSerializer,
    DirectDeserializer,
    DirectSerializer,
)
from dubbo.url import URL
from dubbo.utils import FunctionHelper


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
        """
        Invoke the invocation.
        :param invocation: The invocation to invoke.
        :type invocation: RpcInvocation
        :return: The result of the invocation.
        :rtype: Result
        """
        future = concurrent.futures.Future()
        result = TriResult(future)
        if not self._client.is_connected():
            result.set_exception(
                RemotingError("The client is not connected to the server.")
            )
            return result

        # get method descriptor
        method_descriptor: MethodDescriptor = invocation.get_attribute(
            common_constants.METHOD_DESCRIPTOR_KEY
        )

        # get arg_serializer
        arg_serializing_function = method_descriptor.get_arg_serializer()
        arg_serializer = (
            CustomSerializer(arg_serializing_function)
            if arg_serializing_function
            else DirectSerializer()
        )

        # get return_deserializer
        return_deserializing_function = method_descriptor.get_return_deserializer()
        return_deserializer = (
            CustomDeserializer(return_deserializing_function)
            if return_deserializing_function
            else DirectDeserializer()
        )

        write_stream = TriClientWriteStream()
        read_stream = TriReadStream()

        # create listener
        rpc_type = method_descriptor.get_rpc_type()
        is_unary = not rpc_type.client_stream and not rpc_type.server_stream
        if is_unary:
            listener = FutureToClientCallListenerAdapter(future)
        else:
            read_stream = TriReadStream()
            listener = ReadStreamToClientCallListenerAdapter(read_stream)

        # Create a new TriClientCall
        tri_client_call = TripleClientCall(
            self._stream_multiplexer,
            listener,
            arg_serializer,
            return_deserializer,
        )
        write_stream.set_call(tri_client_call)

        if not is_unary:
            write_stream = TriReadWriteStream(write_stream, read_stream)

        # start the call
        try:
            metadata = self._create_metadata(invocation)
            tri_client_call.start(metadata)
        except ExtensionError as e:
            result.set_exception(e)
            return result

        # write the message
        if not rpc_type.client_stream:
            # if the client call is not a stream, we send the message directly
            FunctionHelper.call_func(write_stream.write, invocation.get_argument())
            write_stream.done_writing()
        else:
            # try to get first argument and check if it is an iterable
            args, _ = invocation.get_argument()
            if args and isinstance(args[0], Iterator):
                # if the argument is an iterator, we need to write the stream
                for arg in args[0]:
                    write_stream.write(arg)
                write_stream.done_writing()

        # If the call is not unary, we need to return the stream
        # server_stream -> return read_stream
        # client_stream or bidirectional_stream -> return write_read_stream
        if not is_unary:
            if rpc_type.server_stream and not rpc_type.client_stream:
                result.set_value(read_stream)
            else:
                result.set_value(write_stream)

        return result

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
