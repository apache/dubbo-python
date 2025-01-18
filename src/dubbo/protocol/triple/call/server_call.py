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

import abc
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from dubbo.classes import ReadWriteStream
from dubbo.loggers import loggerFactory
from dubbo.protocol.triple.call import ServerCall
from dubbo.protocol.triple.constants import (
    GRpcCode,
    TripleHeaderName,
    TripleHeaderValue,
)
from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.protocol.triple.stream import ServerStream
from dubbo.protocol.triple.streams import (
    TriReadStream,
    TriReadWriteStream,
    TriServerWriteStream,
)
from dubbo.proxy.handlers import RpcMethodHandler
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import HttpStatus
from dubbo.serialization import (
    CustomDeserializer,
    CustomSerializer,
    DirectDeserializer,
    DirectSerializer,
)
from dubbo.types import RpcType, RpcTypes
from dubbo.utils import FunctionHelper

_LOGGER = loggerFactory.get_logger()


class TripleServerCall(ServerCall, ServerStream.Listener):
    def __init__(
        self,
        server_stream: ServerStream,
        method_handler: RpcMethodHandler,
        executor: ThreadPoolExecutor,
    ):
        self._server_stream = server_stream
        self._executor = executor

        # create read stream
        self._read_stream = TriReadStream()

        # create write stream
        write_stream = TriServerWriteStream(self)
        read_write_stream = TriReadWriteStream(write_stream, self._read_stream)

        self._method_runner: MethodRunner = MethodRunnerFactory.create(method_handler, read_write_stream)

        # get method descriptor
        method_descriptor = method_handler.method_descriptor

        # get arguments deserializer
        arg_deserializer = method_descriptor.get_arg_deserializer()
        self._deserializer = CustomDeserializer(arg_deserializer) if arg_deserializer else DirectDeserializer()

        # get return serializer
        return_serializer = method_descriptor.get_return_serializer()
        self._serializer = CustomSerializer(return_serializer) if return_serializer else DirectSerializer()

        self._headers_sent = False

    def send_message(self, message: Any) -> None:
        if not self._headers_sent:
            headers = Http2Headers()
            headers.status = HttpStatus.OK.value
            headers.add(
                TripleHeaderName.CONTENT_TYPE.value,
                TripleHeaderValue.APPLICATION_GRPC_PROTO.value,
            )
            self._server_stream.send_headers(headers)

        serialized_data = FunctionHelper.call_func(self._serializer.serialize, message)
        # TODO support compression
        self._server_stream.send_message(serialized_data, False)

    def complete(self, status: TriRpcStatus, attachments: dict[str, Any]) -> None:
        if not attachments.get(TripleHeaderName.CONTENT_TYPE.value):
            attachments[TripleHeaderName.CONTENT_TYPE.value] = TripleHeaderValue.APPLICATION_GRPC_PROTO.value
        self._server_stream.complete(status, attachments)

    def on_headers(self, headers: dict[str, Any]) -> None:
        # start a new thread to run the method
        self._executor.submit(self._method_runner.run)

    def on_message(self, data: bytes) -> None:
        if data == b"":
            return
        deserialized_data = self._deserializer.deserialize(data)
        self._read_stream.put(deserialized_data)

    def on_complete(self) -> None:
        self._read_stream.put_eof()

    def on_cancel_by_remote(self, status: TriRpcStatus) -> None:
        # cancel the method runner.
        self._read_stream.put_exception(status.as_exception())


class MethodRunner(abc.ABC):
    """
    Interface for method runner.
    """

    @abc.abstractmethod
    def run(self) -> None:
        """
        Run the method.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def handle_result(self, result: Any) -> None:
        """
        Handle the result.
        :param result: result
        :type result: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def handle_exception(self, e: Exception) -> None:
        """
        Handle the exception.
        :param e: exception.
        :type e: Exception
        """
        raise NotImplementedError()


class DefaultMethodRunner(MethodRunner):
    """
    Abstract method runner.
    """

    def __init__(
        self,
        func: Callable,
        read_write_stream: ReadWriteStream,
        rpc_type: RpcType,
    ):
        self._read_write_stream = read_write_stream
        self._func = func

        self._rpc_type = rpc_type

    def run(self) -> None:
        try:
            if self._rpc_type == RpcTypes.UNARY.value:
                result = self._func(self._read_write_stream.read())
            else:
                result = self._func(self._read_write_stream)
            # handle the result
            self.handle_result(result)
        except Exception as e:
            # handle the exception
            self.handle_exception(e)

    def handle_result(self, result: Any) -> None:
        try:
            # check if the stream is completed
            if not self._read_write_stream.can_write_more():
                return

            if not self._rpc_type.server_stream:
                # get single result
                self._read_write_stream.write(result)
            else:
                # get multi results
                for message in result:
                    self._read_write_stream.write(message)

            self._read_write_stream.done_writing()
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, e: Exception) -> None:
        if self._read_write_stream.can_write_more():
            _LOGGER.exception("Invoke method failed: %s", e)
            status = TriRpcStatus(
                GRpcCode.INTERNAL,
                description=f"Invoke method failed: {str(e)}",
                cause=e,
            )
            self._read_write_stream.done_writing(tri_rpc_status=status)


class MethodRunnerFactory:
    """
    Factory for method runner.
    """

    @staticmethod
    def create(method_handler: RpcMethodHandler, read_write_stream: ReadWriteStream) -> MethodRunner:
        """
        Create a method runner.

        :param method_handler: method handler
        :type method_handler: RpcMethodHandler
        :param read_write_stream: read write stream
        :type read_write_stream: ReadWriteStream
        :return: method runner
        :rtype: MethodRunner
        """

        method_descriptor = method_handler.method_descriptor

        return DefaultMethodRunner(
            method_descriptor.get_method(),
            read_write_stream,
            method_descriptor.get_rpc_type(),
        )
