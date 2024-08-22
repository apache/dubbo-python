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
from typing import Any, Callable, Dict

from dubbo.deliverers import (
    MessageDeliverer,
    MultiMessageDeliverer,
    SingleMessageDeliverer,
)
from dubbo.protocol.triple.call import ServerCall
from dubbo.protocol.triple.constants import (
    GRpcCode,
    TripleHeaderName,
    TripleHeaderValue,
)
from dubbo.protocol.triple.status import TriRpcStatus
from dubbo.protocol.triple.stream import ServerStream
from dubbo.proxy.handlers import RpcMethodHandler
from dubbo.remoting.aio.http2.headers import Http2Headers
from dubbo.remoting.aio.http2.registries import HttpStatus
from dubbo.serialization import (
    CustomDeserializer,
    CustomSerializer,
    DirectDeserializer,
    DirectSerializer,
)


class TripleServerCall(ServerCall, ServerStream.Listener):

    def __init__(
        self,
        stream: ServerStream,
        method_handler: RpcMethodHandler,
        executor: ThreadPoolExecutor,
    ):
        self._stream = stream
        self._method_runner: MethodRunner = MethodRunnerFactory.create(
            method_handler, self
        )

        self._executor = executor

        # get serializer
        serializing_function = method_handler.response_serializer
        self._serializer = (
            CustomSerializer(serializing_function)
            if serializing_function
            else DirectSerializer()
        )

        # get deserializer
        deserializing_function = method_handler.request_deserializer
        self._deserializer = (
            CustomDeserializer(deserializing_function)
            if deserializing_function
            else DirectDeserializer()
        )

        self._headers_sent = False

    def send_message(self, message: Any) -> None:
        if not self._headers_sent:
            headers = Http2Headers()
            headers.status = HttpStatus.OK.value
            headers.add(
                TripleHeaderName.CONTENT_TYPE.value,
                TripleHeaderValue.APPLICATION_GRPC_PROTO.value,
            )
            self._stream.send_headers(headers)

        serialized_data = self._serializer.serialize(message)
        # TODO support compression
        self._stream.send_message(serialized_data, False)

    def complete(self, status: TriRpcStatus, attachments: Dict[str, Any]) -> None:
        if not attachments.get(TripleHeaderName.CONTENT_TYPE.value):
            attachments[TripleHeaderName.CONTENT_TYPE.value] = (
                TripleHeaderValue.APPLICATION_GRPC_PROTO.value
            )
        self._stream.complete(status, attachments)

    def on_headers(self, headers: Dict[str, Any]) -> None:
        # start a new thread to run the method
        self._executor.submit(self._method_runner.run)

    def on_message(self, data: bytes) -> None:
        deserialized_data = self._deserializer.deserialize(data)
        self._method_runner.receive_arg(deserialized_data)

    def on_complete(self) -> None:
        self._method_runner.receive_complete()

    def on_cancel_by_remote(self, status: TriRpcStatus) -> None:
        # cancel the method runner.
        self._executor.shutdown()
        self._executor = None


class MethodRunner(abc.ABC):
    """
    Interface for method runner.
    """

    @abc.abstractmethod
    def receive_arg(self, arg: Any) -> None:
        """
        Receive argument.
        :param arg: argument
        :type arg: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def receive_complete(self) -> None:
        """
        Receive complete.
        """
        raise NotImplementedError()

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
        server_call: TripleServerCall,
        client_stream: bool,
        server_stream: bool,
    ):

        self._server_call: TripleServerCall = server_call
        self._func = func

        self._deliverer: MessageDeliverer = (
            MultiMessageDeliverer() if client_stream else SingleMessageDeliverer()
        )
        self._server_stream = server_stream

        self._completed = False

    def receive_arg(self, arg: Any) -> None:
        self._deliverer.add(arg)

    def receive_complete(self) -> None:
        self._deliverer.complete()

    def run(self) -> None:
        try:
            if isinstance(self._deliverer, SingleMessageDeliverer):
                result = self._func(self._deliverer.get())
            else:
                result = self._func(self._deliverer)
            # handle the result
            self.handle_result(result)
        except Exception as e:
            # handle the exception
            self.handle_exception(e)

    def handle_result(self, result: Any) -> None:
        try:
            if not self._server_stream:
                # get single result
                self._server_call.send_message(result)
            else:
                # get multi results
                for message in result:
                    self._server_call.send_message(message)

            self._server_call.complete(TriRpcStatus(GRpcCode.OK), {})
            self._completed = True
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, e: Exception) -> None:
        if not self._completed:
            status = TriRpcStatus(
                GRpcCode.INTERNAL,
                description=f"Invoke method failed: {str(e)}",
                cause=e,
            )
            self._server_call.complete(status, {})
            self._completed = True


class MethodRunnerFactory:
    """
    Factory for method runner.
    """

    @staticmethod
    def create(method_handler: RpcMethodHandler, server_call) -> MethodRunner:
        """
        Create a method runner.

        :param method_handler: method handler
        :type method_handler: RpcMethodHandler
        :param server_call: server call
        :type server_call: TripleServerCall
        :return: method runner
        :rtype: MethodRunner
        """

        call_type = method_handler.call_type

        return DefaultMethodRunner(
            method_handler.behavior,
            server_call,
            call_type.client_stream,
            call_type.server_stream,
        )
