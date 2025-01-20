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

from dubbo.node import Node
from dubbo.url import URL

__all__ = ["Registry", "RegistryFactory", "NotifyListener"]


class NotifyListener(abc.ABC):
    """
    The notify listener.
    """

    @abc.abstractmethod
    def notify(self, urls: list[URL]) -> None:
        """
        Notify the listener.

        :param urls: The list of registered information , is always not empty.
        """
        raise NotImplementedError()


class Registry(Node, abc.ABC):
    @abc.abstractmethod
    def register(self, url: URL) -> None:
        """
        Register a service to registry.

        :param url: The service URL.
        :type url: URL
        :return: None
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def unregister(self, url: URL) -> None:
        """
        Unregister a service from registry.

        :param url: The service URL.
        :type url: URL
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def subscribe(self, url: URL, listener: NotifyListener) -> None:
        """
        Subscribe a service from registry.
        :param url: The service URL.
        :type url: URL
        :param listener: The listener to notify when service changed.
        :type listener: NotifyListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def unsubscribe(self, url: URL, listener: NotifyListener) -> None:
        """
        Unsubscribe a service from registry.
        :param url: The service URL.
        :type url: URL
        :param listener: The listener to notify when service changed.
        :type listener: NotifyListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def lookup(self, url: URL) -> None:
        """
        Lookup a service from registry.
        :param url: The service URL.
        :type url: URL
        """
        raise NotImplementedError()


class RegistryFactory(abc.ABC):
    @abc.abstractmethod
    def get_registry(self, url: URL) -> Registry:
        """
        Get a registry instance.

        :param url: The registry URL.
        :type url: URL
        :return: The registry instance.
        :rtype: Registry
        """
        raise NotImplementedError()
