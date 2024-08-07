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
import enum

from dubbo.common import URL

__all__ = [
    "StateListener",
    "DataListener",
    "ChildrenListener",
    "ZookeeperClient",
    "ZookeeperTransport",
]


class StateListener(abc.ABC):
    class State(enum.Enum):
        """
        Zookeeper connection state.
        """

        SUSPENDED = "SUSPENDED"
        CONNECTED = "CONNECTED"
        LOST = "LOST"

    @abc.abstractmethod
    def state_changed(self, state: "StateListener.State") -> None:
        """
        Notify when connection state changed.

        :param StateListener.State state: The new connection state.
        """
        raise NotImplementedError()


class DataListener(abc.ABC):
    class EventType(enum.Enum):
        """
        Zookeeper data event type.
        """

        CREATED = "CREATED"
        DELETED = "DELETED"
        CHANGED = "CHANGED"
        CHILD = "CHILD"
        NONE = "NONE"

    @abc.abstractmethod
    def data_changed(
        self, path: str, data: bytes, event_type: "DataListener.EventType"
    ) -> None:
        """
        Notify when data changed.

        :param str path: The node path.
        :param bytes data: The new data.
        :param DataListener.EventType event_type: The event type.
        """
        raise NotImplementedError()


class ChildrenListener(abc.ABC):
    @abc.abstractmethod
    def children_changed(self, path: str, children: list) -> None:
        """
        Notify when children changed.

        :param str path: The node path.
        :param list children: The new children.
        """
        raise NotImplementedError()


class ZookeeperClient(abc.ABC):
    """
    Zookeeper Client interface.
    """

    __slots__ = ["_url"]

    def __init__(self, url: URL):
        """
        Initialize the zookeeper client.

        :param URL url: The zookeeper URL.
        """
        self._url = url

    @abc.abstractmethod
    def start(self) -> None:
        """
        Start the zookeeper client.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def stop(self) -> None:
        """
        Stop the zookeeper client.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the client is connected to zookeeper.

        :return: True if connected, False otherwise.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def create(self, path: str, ephemeral=False) -> None:
        """
        Create a node in zookeeper.

        :param str path: The node path.
        :param bool ephemeral: Whether the node is ephemeral. False: persistent, True: ephemeral.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def create_or_update(self, path: str, data: bytes, ephemeral=False) -> None:
        """
        Create or update a node in zookeeper.

        :param str path: The node path.
        :param bytes data: The node data.
        :param bool ephemeral: Whether the node is ephemeral. False: persistent, True: ephemeral.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def check_exist(self, path: str) -> bool:
        """
        Check if a node exists in zookeeper.

        :param str path: The node path.
        :return: True if the node exists, False otherwise.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_data(self, path: str) -> bytes:
        """
        Get data of a node in zookeeper.

        :param str path: The node path.
        :return: The node data.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_children(self, path: str) -> list:
        """
        Get children of a node in zookeeper.

        :param str path: The node path.
        :return: The children of the node.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def delete(self, path: str) -> None:
        """
        Delete a node in zookeeper.

        :param str path: The node path.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_state_listener(self, listener: StateListener) -> None:
        """
        Add a state listener to zookeeper.

        :param StateListener listener: The listener to notify when connection state changed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_state_listener(self, listener: StateListener) -> None:
        """
        Remove a state listener from zookeeper.

        :param StateListener listener: The listener to remove.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_data_listener(self, path: str, listener: DataListener) -> None:
        """
        Add a data listener to a node in zookeeper.

        :param str path: The node path.
        :param DataListener listener: The listener to notify when data changed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_data_listener(self, listener: DataListener) -> None:
        """
        Remove a data listener from a node in zookeeper.

        :param DataListener listener: The listener to remove.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_children_listener(self, path: str, listener: ChildrenListener) -> None:
        """
        Add a children listener to a node in zookeeper.

        :param str path: The node path.
        :param ChildrenListener listener: The listener to notify when children changed.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_children_listener(self, listener: ChildrenListener) -> None:
        """
        Remove a children listener from a node in zookeeper.

        :param ChildrenListener listener: The listener to remove.
        """
        raise NotImplementedError()


class ZookeeperTransport(abc.ABC):

    @abc.abstractmethod
    def connect(self, url: URL) -> ZookeeperClient:
        """
        Connect to a zookeeper.
        """
        raise NotImplementedError()
