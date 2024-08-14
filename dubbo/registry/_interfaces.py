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
from typing import List

from dubbo.node import Node
from dubbo.url import URL

__all__ = ["Registry", "RegistryFactory"]


class NotifyListener(abc.ABC):
    """
    The notify listener.
    """

    @abc.abstractmethod
    def notify(self, urls: List[URL]) -> None:
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

        :param URL url: The service URL.
        :return: None
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def unregister(self, url: URL) -> None:
        """
        Unregister a service from registry.

        :param URL url: The service URL.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def subscribe(self, url: URL, listener):
        """
        Subscribe a service from registry.
        :param URL url: The service URL.
        :param listener: The listener to notify when service changed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def unsubscribe(self, url: URL, listener):
        """
        Unsubscribe a service from registry.
        :param URL url: The service URL.
        :param listener: The listener to notify when service changed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def lookup(self, url: URL):
        """
        Lookup a service from registry.
        :param URL url: The service URL.
        """
        raise NotImplementedError()


class RegistryFactory(abc.ABC):

    @abc.abstractmethod
    def get_registry(self, url: URL) -> Registry:
        """
        Get a registry instance.

        :param URL url: The registry URL.
        :return: The registry instance.
        """
        raise NotImplementedError()
