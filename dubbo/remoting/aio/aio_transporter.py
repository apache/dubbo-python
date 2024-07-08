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
import threading
import uuid
from typing import Optional, Tuple

from dubbo.constants import common_constants
from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio import loop
from dubbo.remoting.transporter import Client, Server, Transporter
from dubbo.url import URL

logger = loggerFactory.get_logger(__name__)


class AioClient(Client):
    """
    Asyncio client.
    Args:
        url(URL): The configuration of the client.
    """

    def __init__(self, url: URL):
        super().__init__(url)

        # Set the side of the transporter to client.
        self._url.add_parameter(
            common_constants.TRANSPORTER_SIDE_KEY,
            common_constants.TRANSPORTER_SIDE_CLIENT,
        )

        # Set connection closed function
        def _connection_lost(exc: Optional[Exception]) -> None:
            if exc:
                logger.error("Connection lost", exc)
            self._connected = False

        self._url.add_attribute(
            common_constants.TRANSPORTER_ON_CONN_CLOSE_KEY, _connection_lost
        )

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._transport: Optional[asyncio.Transport] = None
        self._protocol: Optional[asyncio.Protocol] = None

        self._closing = False

        # Open and connect the client
        self.open()
        self.connect()

    def open(self) -> None:
        """
        Create a thread and run asyncio loop in it.
        """
        self._loop, self._thread = loop.start_loop_in_thread(
            f"dubbo-aio-client-{uuid.uuid4()}"
        )
        self._opened = True

    def _create_protocol(self) -> asyncio.Protocol:
        """
        Create the protocol.
        """

        return self._url.attributes["protocol"](self._url)

    def connect(self) -> None:
        """
        Connect to the server.
        """
        if not self._opened:
            raise RuntimeError("The client is not opened yet.")
        elif self._closed:
            raise RuntimeError("The client is closed.")

        async def _inner_connect() -> Tuple[asyncio.Transport, asyncio.Protocol]:
            running_loop = asyncio.get_running_loop()

            transport, protocol = await running_loop.create_connection(
                lambda: self._url.get_attribute("protocol")(self._url),
                self._url.host,
                self._url.port,
            )
            return transport, protocol

        future = asyncio.run_coroutine_threadsafe(_inner_connect(), self._loop)

        try:
            self._transport, self._protocol = future.result()
            self._connected = True
            logger.info(
                f"Connected to the server: ip={self._url.host}, port={self._url.port}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to the server: {e}")
            raise e

    def close(self) -> None:
        """
        Close the client. just stop the transport.
        """
        if not self._opened:
            raise RuntimeError("The client is not opened yet.")
        if self._closing or self._closed:
            return

        self._closing = True

        try:
            # Close the transport
            self._transport.close()
            self._connected = False
            # Stop the loop
            loop.stop_loop_in_thread(self._loop, self._thread)
            self._closed = True
        finally:
            self._closing = False


class AioServer(Server):
    """
    Asyncio server.
    """

    def __init__(self, url: URL):
        self._url = url
        # Set the side of the transporter to server.
        self._url.add_parameter(
            common_constants.TRANSPORTER_SIDE_KEY,
            common_constants.TRANSPORTER_SIDE_SERVER,
        )
        # TODO implement the server


class AioTransporter(Transporter):
    """
    Asyncio transporter.
    """

    def connect(self, url: URL) -> Client:
        return AioClient(url)

    def bind(self, url: URL) -> Server:
        return AioServer(url)
