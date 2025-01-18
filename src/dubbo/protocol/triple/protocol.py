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
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.loggers import loggerFactory
from dubbo.protocol import Invoker, Protocol
from dubbo.protocol.triple.invoker import TripleInvoker
from dubbo.protocol.triple.stream.server_stream import ServerTransportListener
from dubbo.proxy.handlers import RpcServiceHandler
from dubbo.remoting import Server, Transporter
from dubbo.remoting.aio import constants as aio_constants
from dubbo.remoting.aio.http2.protocol import Http2ClientProtocol, Http2ServerProtocol
from dubbo.remoting.aio.http2.stream_handler import (
    StreamClientMultiplexHandler,
    StreamServerMultiplexHandler,
)
from dubbo.url import URL

_LOGGER = loggerFactory.get_logger()


class TripleProtocol(Protocol):
    """
    Triple protocol.
    """

    __slots__ = ["_url", "_transporter", "_invokers"]

    def __init__(self):
        self._transporter: Transporter = extensionLoader.get_extension(
            Transporter, common_constants.TRANSPORTER_DEFAULT_VALUE
        )()
        self._invokers = []
        self._server: Optional[Server] = None

        self._path_resolver: dict[str, RpcServiceHandler] = {}

    def export(self, url: URL):
        """
        Export a service.
        """
        if self._server is not None:
            return

        service_handler = url.attributes[common_constants.SERVICE_HANDLER_KEY]

        if isinstance(service_handler, Iterable):
            for handler in service_handler:
                self._path_resolver[handler.service_name] = handler
        else:
            self._path_resolver[service_handler.service_name] = service_handler

        method_executor = ThreadPoolExecutor(thread_name_prefix=f"dubbo_tri_method_{str(uuid.uuid4())}", max_workers=10)

        listener_factory = functools.partial(ServerTransportListener, self._path_resolver, method_executor)

        # Create a stream handler
        stream_multiplexer = StreamServerMultiplexHandler(listener_factory)
        # set stream handler and protocol
        url.attributes[aio_constants.STREAM_HANDLER_KEY] = stream_multiplexer
        url.attributes[common_constants.PROTOCOL_KEY] = Http2ServerProtocol

        # Create a server
        self._server = self._transporter.bind(url)

    def refer(self, url: URL) -> Invoker:
        """
        Refer a remote service.
        :param url: The URL.
        :type url: URL
        """
        # Create a stream handler
        stream_multiplexer = StreamClientMultiplexHandler()
        # set stream handler and protocol
        url.attributes[aio_constants.STREAM_HANDLER_KEY] = stream_multiplexer
        url.attributes[common_constants.PROTOCOL_KEY] = Http2ClientProtocol

        # Create a client
        client = self._transporter.connect(url)
        invoker = TripleInvoker(url, client, stream_multiplexer)
        self._invokers.append(invoker)
        return invoker
