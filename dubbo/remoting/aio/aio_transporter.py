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
import concurrent
from typing import Optional

from dubbo.constants import common_constants
from dubbo.loggers import loggerFactory
from dubbo.remoting._interfaces import Client, Server, Transporter
from dubbo.remoting.aio import constants as aio_constants
from dubbo.remoting.aio.event_loop import EventLoop
from dubbo.remoting.aio.exceptions import RemotingError
from dubbo.url import URL
from dubbo.utils import FutureHelper

_LOGGER = loggerFactory.get_logger()


class AioClient(Client):
    """
    Asyncio client.
    """

    __slots__ = [
        "_protocol",
        "_connected",
        "_close_future",
        "_closing",
        "_closed",
        "_event_loop",
    ]

    def __init__(self, url: URL):
        """
        Initialize the client.
        :param url: The URL.
        :type url: URL
        """
        super().__init__(url)

        # Set the side of the transporter to client.
        self._protocol = None

        # the event to indicate the connection status of the client
        self._connected = False

        # the event to indicate the close status of the client
        self._close_future = concurrent.futures.Future()
        self._closing = False
        self._closed = False

        self._url.parameters[common_constants.SIDE_KEY] = common_constants.CLIENT_VALUE
        self._url.attributes[aio_constants.CLOSE_FUTURE_KEY] = self._close_future

        self._event_loop: Optional[EventLoop] = None

        # connect to the server
        self.connect()

    def is_connected(self) -> bool:
        """
        Check if the client is connected.
        """
        return self._connected

    def is_closed(self) -> bool:
        """
        Check if the client is closed.
        """
        return self._closed or self._closing

    def reconnect(self) -> None:
        """
        Reconnect to the server.
        """
        self.close()
        self._connected = False
        self._close_future = concurrent.futures.Future()
        self.connect()

    def connect(self) -> None:
        """
        Connect to the server.
        """
        if self.is_connected():
            return
        elif self.is_closed():
            raise RemotingError("The client is closed.")

        async def _inner_operation():
            running_loop = asyncio.get_running_loop()
            # Create the connection.
            _, protocol = await running_loop.create_connection(
                lambda: self._url.attributes[common_constants.PROTOCOL_KEY](self._url),
                self._url.host,
                self._url.port,
            )
            # Set the protocol.
            return protocol

        # Run the connection logic in the event loop.
        if self._event_loop:
            self._event_loop.stop()
        self._event_loop = EventLoop()
        self._event_loop.start()

        future = asyncio.run_coroutine_threadsafe(
            _inner_operation(), self._event_loop.loop
        )
        try:
            self._protocol = future.result()
            self._connected = True
            _LOGGER.info(
                "Connected to the server. host: %s, port: %s",
                self._url.host,
                self._url.port,
            )
        except ConnectionRefusedError as e:
            raise RemotingError("Failed to connect to the server") from e

    def close(self) -> None:
        """
        Close the client.
        """
        if self.is_closed():
            return
        self._closing = True

        def _on_close(_future: concurrent.futures.Future):
            self._closed = True if _future.done() else False

        self._close_future.add_done_callback(_on_close)

        try:
            self._protocol.close()
            exc = self._close_future.exception()
            if exc:
                raise RemotingError(f"Failed to close the client: {exc}")
            _LOGGER.info("Closed the client.")
        finally:
            self._event_loop.stop()
            self._closing = False


class AioServer(Server):
    """
    Asyncio server.
    """

    def __init__(self, url: URL):
        self._url = url
        # Set the side of the transporter to server.
        self._url.parameters[common_constants.SIDE_KEY] = common_constants.SERVER_VALUE

        # the event to indicate the close status of the server
        self._event_loop = EventLoop()
        self._event_loop.start()

        # Whether the server is exporting
        self._exporting = False
        # Whether the server is exported
        self._exported = False

        # Whether the server is closing
        self._closing = False
        # Whether the server is closed
        self._closed = False

        # start the server
        self.export()

    def is_exported(self) -> bool:
        return self._exported or self._exporting

    def is_closed(self) -> bool:
        return self._closed or self._closing

    def export(self):
        """
        Export the server.
        """
        if self.is_exported():
            return
        elif self.is_closed():
            raise RemotingError("The server is closed.")

        async def _inner_operation(_future: concurrent.futures.Future):
            try:
                running_loop = asyncio.get_running_loop()
                server = await running_loop.create_server(
                    lambda: self._url.attributes[common_constants.PROTOCOL_KEY](
                        self._url
                    ),
                    self._url.host,
                    self._url.port,
                )

                # Serve the server forever
                async with server:
                    FutureHelper.set_result(_future, None)
                    await server.serve_forever()
            except Exception as e:
                FutureHelper.set_exception(_future, e)

        # Run the server logic in the event loop.
        future = concurrent.futures.Future()
        asyncio.run_coroutine_threadsafe(
            _inner_operation(future), self._event_loop.loop
        )

        try:
            exc = future.exception()
            if exc:
                raise RemotingError("Failed to export the server") from exc
            else:
                self._exported = True
            _LOGGER.info("Exported the server. port: %s", self._url.port)
        finally:
            self._exporting = False

    def close(self):
        """
        Close the server.
        """
        if self.is_closed():
            return
        self._closing = True

        try:
            self._event_loop.stop()
            self._closed = True
        except Exception as e:
            raise RemotingError("Failed to close the server") from e
        finally:
            self._closing = False


class AioTransporter(Transporter):
    """
    Asyncio transporter.
    """

    def connect(self, url: URL) -> Client:
        return AioClient(url)

    def bind(self, url: URL) -> Server:
        return AioServer(url)
