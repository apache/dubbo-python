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
import asyncio

from h2.config import H2Configuration

from dubbo.common.url import URL
from dubbo.logger.logger_factory import loggerFactory
from dubbo.loop import loopManager
from dubbo.remoting.aio.http2_protocol import Http2Protocol
from dubbo.remoting.transporter import (RemotingClient, RemotingServer,
                                        Transporter)

logger = loggerFactory.get_logger(__name__)


class AioTransporter(Transporter):
    """
    Asyncio transporter.
    """

    def bind(self, url: URL) -> RemotingServer:
        return AioServer()

    def connect(self, url: URL) -> RemotingClient:
        return AioClient(url)


class AioClient(RemotingClient):
    """
    Asyncio client.
    """
    def __init__(self, url: URL):
        self.url = url
        self._protocol = None
        self._transport = None
        self._loop = loopManager.get_client_loop()

        self._closed = False

    async def _create_connect(self):
        transport, protocol = await self._loop.create_connection(
            lambda: Http2Protocol(
                H2Configuration(client_side=True, header_encoding="utf-8")
            ),
            self.url.host,
            self.url.port if self.url.port else None,
        )
        return transport, protocol

    def start(self):
        future = asyncio.run_coroutine_threadsafe(self._create_connect(), self._loop)
        try:
            self._transport, self._protocol = future.result()
        except Exception:
            logger.exception("Failed to create connection.")
            self._transport = None
            self._protocol = None

    def is_available(self) -> bool:
        if self._closed:
            return False
        return self._transport and not self._transport.is_closing()

    async def send(self, data: bytes):
        self._protocol.send_data(data)

    async def close(self):
        self._closed = True
        self._transport.close()
        await self._transport.wait_closed()


class AioServer(RemotingServer):
    """
    Asyncio server.
    """
    pass
