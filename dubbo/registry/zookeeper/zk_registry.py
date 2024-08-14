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
from typing import Dict, List

from dubbo.constants import common_constants, registry_constants
from dubbo.loggers import loggerFactory
from dubbo.registry import Registry, RegistryFactory
from dubbo.registry.zookeeper import ChildrenListener, StateListener, ZookeeperTransport
from dubbo.registry.zookeeper.kazoo_transport import KazooZookeeperTransport
from dubbo.url import URL

__all__ = ["ZookeeperRegistryFactory", "ZookeeperRegistry"]

_LOGGER = loggerFactory.get_logger()


class _DefaultStateListener(StateListener):
    def state_changed(self, state: "StateListener.State") -> None:
        if state == StateListener.State.LOST:
            _LOGGER.warning("Connection lost")
        elif state == StateListener.State.CONNECTED:
            _LOGGER.info("Connection established")
        elif state == StateListener.State.SUSPENDED:
            _LOGGER.info("Connection suspended")


class ZookeeperRegistry(Registry):
    """
    Zookeeper registry implementation.
    """

    # default root is "dubbo"
    DEFAULT_ROOT = common_constants.DUBBO_VALUE

    def __init__(self, url: URL, zk_transport: ZookeeperTransport):
        self._url = url
        self._any_services = set()
        self._zk_listeners: Dict[URL, Dict[object, ChildrenListener]] = {}

        # connect to the zookeeper server
        self._zk_client = zk_transport.connect(self._url)

        # get the root path
        self._root = common_constants.PATH_SEPARATOR + url.parameters.get(
            common_constants.GROUP_KEY, self.DEFAULT_ROOT
        ).lstrip(common_constants.PATH_SEPARATOR)

        # add the state listener
        self._zk_client.add_state_listener(_DefaultStateListener())

    @property
    def root_dir(self) -> str:
        """
        Get the root directory.
        :return: the root directory.
        :rtype: str
        """
        if common_constants.PATH_SEPARATOR == self._root:
            return self._root
        return self._root + common_constants.PATH_SEPARATOR

    @property
    def root_path(self) -> str:
        """
        Get the root path.
        :return: the root path.
        :rtype: str
        """
        return self.root_dir

    def register(self, url: URL) -> None:
        self._zk_client.create(
            self.to_url_path(url),
            url.location.encode("utf-8"),
            ephemeral=bool(url.parameters.get(registry_constants.DYNAMIC_KEY, True)),
        )

    def unregister(self, url: URL) -> None:
        self._zk_client.delete(self.to_url_path(url))

    def subscribe(self, url: URL, listener):
        pass

    def unsubscribe(self, url: URL, listener):
        pass

    def lookup(self, url: URL):
        providers = []
        for category_path in self.get_categories_path(url):
            children_list = self._zk_client.get_children(category_path)
            if children_list:
                providers.extend(children_list)
        return providers

    def get_service_path(self, url: URL) -> str:
        """
        Get the service path.
        :param url: The URL.
        :type url: URL
        :return: The service path.
        :rtype: str
        """
        service_path = url.parameters.get(common_constants.SERVICE_KEY, url.path)
        if service_path == common_constants.ANY_VALUE:
            return self.root_path
        return self.root_dir + service_path

    def get_category_path(self, url: URL) -> str:
        """
        Get the category path.
        :param url: The URL.
        :type url: URL
        :return: The category path.
        :rtype: str
        """
        category = url.parameters.get(
            registry_constants.CATEGORY_KEY, registry_constants.PROVIDERS_CATEGORY
        )
        return self.get_service_path(url) + common_constants.PATH_SEPARATOR + category

    def get_categories_path(self, url: URL) -> List[str]:
        """
        Get the categories' path.
        :param url: The URL.
        :type url: URL
        :return: The categories' paths.
        :rtype: List[str]
        """
        # get the categories
        if common_constants.ANY_VALUE == url.parameters.get(
            registry_constants.CATEGORY_KEY
        ):
            categories = [
                registry_constants.PROVIDERS_CATEGORY,
                registry_constants.CONSUMERS_CATEGORY,
            ]
        else:
            parameter = url.parameters.get(
                registry_constants.CATEGORY_KEY, registry_constants.PROVIDERS_CATEGORY
            )
            categories = [
                s.strip() for s in parameter.split(common_constants.COMMA_SEPARATOR)
            ]

        # get paths
        return [
            self.get_service_path(url) + common_constants.PATH_SEPARATOR + category
            for category in categories
        ]

    def to_url_path(self, url: URL) -> str:
        """
        Convert the URL to the path.
        :param url: The URL.
        :type url: URL
        :return: The path.
        :rtype: str
        """
        # return the path
        return (
            self.get_category_path(url)
            + common_constants.PATH_SEPARATOR
            + url.to_str(encode=True)
        )

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
