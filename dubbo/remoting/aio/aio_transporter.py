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
import threading
from typing import Optional

from dubbo.constants import common_constants
from dubbo.logger.logger_factory import loggerFactory
from dubbo.remoting.aio.event_loop import EventLoop
from dubbo.remoting.aio.exceptions import RemotingException
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
        self._protocol = None

        # the event to indicate the connection status of the client
        self._connect_event = threading.Event()
        # the event to indicate the close status of the client
        self._close_future = concurrent.futures.Future()
        self._closing = False

        self._url.add_parameter(
            common_constants.TRANSPORTER_SIDE_KEY,
            common_constants.TRANSPORTER_SIDE_CLIENT,
        )
        self._url.attributes["connect-event"] = self._connect_event
        self._url.attributes["close-future"] = self._close_future

        self._event_loop: Optional[EventLoop] = None

        # connect to the server
        self.connect()

    def is_connected(self) -> bool:
        """
        Check if the client is connected.
        """
        return self._connect_event.is_set()

    def is_closed(self) -> bool:
        """
        Check if the client is closed.
        """
        return self._close_future.done() or self._closing

    def reconnect(self) -> None:
        """
        Reconnect to the server.
        """
        self.close()
        self._connect_event = threading.Event()
        self._close_future = concurrent.futures.Future()
        self.connect()

    def connect(self) -> None:
        """
        Connect to the server.
        """
        if self.is_connected():
            return
        elif self.is_closed():
            raise RemotingException("The client is closed.")

        async def _inner_operate():
            running_loop = asyncio.get_running_loop()
            _, protocol = await running_loop.create_connection(
                lambda: self._url.attributes[common_constants.TRANSPORTER_PROTOCOL_KEY](
                    self._url
                ),
                self._url.host,
                self._url.port,
            )
            return protocol

        # Run the connection logic in the event loop.
        if self._event_loop:
            self._event_loop.stop()
        self._event_loop = EventLoop()
        self._event_loop.start()

        future = asyncio.run_coroutine_threadsafe(
            _inner_operate(), self._event_loop.loop
        )
        try:
            self._protocol = future.result()
        except ConnectionRefusedError as e:
            raise RemotingException("Failed to connect to the server") from e

    def close(self) -> None:
        """
        Close the client.
        """
        if self.is_closed():
            return

        self._closing = True
        try:
            self._protocol.close()
            if exc := self._protocol.exception():
                raise RemotingException(f"Failed to close the client: {exc}")
        except Exception as e:
            if not isinstance(e, RemotingException):
                # Ignore the exception if it is not RemotingException
                pass
            else:
                # Re-raise RemotingException
                raise e
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


class AioTransporter(Transporter):
    """
    Asyncio transporter.
    """

    def connect(self, url: URL) -> Client:
        return AioClient(url)

    def bind(self, url: URL) -> Server:
        return AioServer(url)
