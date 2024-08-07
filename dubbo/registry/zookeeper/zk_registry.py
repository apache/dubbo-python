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

from dubbo.common import URL
from dubbo.common import constants as common_constants
from dubbo.logger import loggerFactory
from dubbo.registry import Registry, RegistryFactory

from ._interfaces import StateListener, ZookeeperTransport
from .kazoo_transport import KazooZookeeperTransport

_LOGGER = loggerFactory.get_logger(__name__)


class ZookeeperRegistry(Registry):
    DEFAULT_ROOT = "dubbo"

    def __init__(self, url: URL, zk_transport: ZookeeperTransport):
        self._url = url
        self._zk_client = zk_transport.connect(self._url)

        self._root = self._url.parameters.get(
            common_constants.GROUP_KEY, self.DEFAULT_ROOT
        )
        if not self._root.startswith(common_constants.PATH_SEPARATOR):
            self._root = common_constants.PATH_SEPARATOR + self._root

        class _StateListener(StateListener):
            def state_changed(self, state: "StateListener.State") -> None:
                if state == StateListener.State.LOST:
                    _LOGGER.warning("Connection lost")
                elif state == StateListener.State.CONNECTED:
                    _LOGGER.info("Connection established")
                elif state == StateListener.State.SUSPENDED:
                    _LOGGER.info("Connection suspended")

        self._zk_client.add_state_listener(_StateListener())

    def register(self, url: URL) -> None:
        pass

    def unregister(self, url: URL) -> None:
        pass

    def subscribe(self, url: URL, listener):
        pass

    def unsubscribe(self, url: URL, listener):
        pass

    def lookup(self, url: URL):
        pass

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._zk_client and self._zk_client.is_connected()

    def destroy(self) -> None:
        if self._zk_client:
            self._zk_client.stop()

    def check_destroy(self) -> None:
        if not self._zk_client:
            raise RuntimeError("registry is destroyed")


class ZookeeperRegistryFactory(RegistryFactory):

    def __init__(self):
        self._transport: ZookeeperTransport = KazooZookeeperTransport()

    def get_registry(self, url: URL) -> Registry:
        return ZookeeperRegistry(url, self._transport)
