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

import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from dubbo.common import constants as common_constants
from dubbo.common.url import URL
from dubbo.extension import extensionLoader
from dubbo.logger import loggerFactory
from dubbo.protocol import Invoker, Protocol
from dubbo.protocol.triple.invoker import TripleInvoker
from dubbo.protocol.triple.stream.server_stream import ServerTransportListener
from dubbo.proxy.handlers import RpcServiceHandler
from dubbo.remoting import Server, Transporter
from dubbo.remoting.aio import constants as aio_constants
from dubbo.remoting.aio.http2.protocol import Http2Protocol
from dubbo.remoting.aio.http2.stream_handler import (
    StreamClientMultiplexHandler,
    StreamServerMultiplexHandler,
)

_LOGGER = loggerFactory.get_logger(__name__)


class TripleProtocol(Protocol):
    """
    Triple protocol.
    """

    __slots__ = ["_url", "_transporter", "_invokers"]

    def __init__(self, url: URL):
        self._url = url
        self._transporter: Transporter = extensionLoader.get_extension(
            Transporter,
            self._url.parameters.get(
                common_constants.TRANSPORTER_KEY,
                common_constants.TRANSPORTER_DEFAULT_VALUE,
            ),
        )()
        self._invokers = []
        self._server: Optional[Server] = None

        self._path_resolver: Dict[str, RpcServiceHandler] = {}

    def export(self, url: URL):
        """
        Export a service.
        """
        if self._server is not None:
            return

        service_handler: RpcServiceHandler = url.attributes[
            common_constants.SERVICE_HANDLER_KEY
        ]

        self._path_resolver[service_handler.service_name] = service_handler

        def listener_factory(_path_resolver):
            return ServerTransportListener(_path_resolver)

        fn = functools.partial(listener_factory, self._path_resolver)

        # Create a stream handler
        executor = ThreadPoolExecutor(thread_name_prefix="dubbo-tri-")
        stream_multiplexer = StreamServerMultiplexHandler(fn, executor)
        # set stream handler and protocol
        url.attributes[aio_constants.STREAM_HANDLER_KEY] = stream_multiplexer
        url.attributes[common_constants.PROTOCOL_KEY] = Http2Protocol

        # Create a server
        self._server = self._transporter.bind(url)

    def refer(self, url: URL) -> Invoker:
        """
        Refer a remote service.
        :param url: The URL.
        :type url: URL
        """
        executor = ThreadPoolExecutor(thread_name_prefix="dubbo-tri-")
        # Create a stream handler
        stream_multiplexer = StreamClientMultiplexHandler(executor)
        # set stream handler and protocol
        url.attributes[aio_constants.STREAM_HANDLER_KEY] = stream_multiplexer
        url.attributes[common_constants.PROTOCOL_KEY] = Http2Protocol

        # Create a client
        client = self._transporter.connect(url)
        invoker = TripleInvoker(url, client, stream_multiplexer)
        self._invokers.append(invoker)
        return invoker
