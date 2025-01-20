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

from dubbo.url import URL

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

        :param state: The new connection state.
        :type state: StateListener.State
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
    def data_changed(self, path: str, data: bytes, event_type: "DataListener.EventType") -> None:
        """
        Notify when data changed.

        :param path: The node path.
        :type path: str
        :param data: The new data.
        :type data: bytes
        :param event_type: The event type.
        :type event_type: DataListener.EventType
        """
        raise NotImplementedError()


class ChildrenListener(abc.ABC):
    @abc.abstractmethod
    def children_changed(self, path: str, children: list) -> None:
        """
        Notify when children changed.

        :param path: The node path.
        :type path: str
        :param children: The new children.
        :type children: list
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

        :param url: The zookeeper URL.
        :type url: URL
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
    def create(self, path: str, data: bytes = b"", ephemeral=False) -> None:
        """
        Create a node in zookeeper.

        :param path: The node path.
        :type path: str
        :param data: The node data.
        :type data: bytes
        :param  ephemeral: Whether the node is ephemeral. False: persistent, True: ephemeral.
        :type  ephemeral: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def create_or_update(self, path: str, data: bytes, ephemeral=False) -> None:
        """
        Create or update a node in zookeeper.

        :param path: The node path.
        :type path: str
        :param data: The node data.
        :type data: bytes
        :param ephemeral: Whether the node is ephemeral. False: persistent, True: ephemeral.
        :type ephemeral: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def check_exist(self, path: str) -> bool:
        """
        Check if a node exists in zookeeper.

        :param path: The node path.
        :type path: str
        :return: True if the node exists, False otherwise.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_data(self, path: str) -> bytes:
        """
        Get data of a node in zookeeper.

        :param path: The node path.
        :type path: str
        :return: The node data.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_children(self, path: str) -> list:
        """
        Get children of a node in zookeeper.

        :param path: The node path.
        :type path: str
        :return: The children of the node.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def delete(self, path: str) -> None:
        """
        Delete a node in zookeeper.

        :param path: The node path.
        :type path: str
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_state_listener(self, listener: StateListener) -> None:
        """
        Add a state listener to zookeeper.

        :param listener: The listener to notify when connection state changed.
        :type listener: StateListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_state_listener(self, listener: StateListener) -> None:
        """
        Remove a state listener from zookeeper.

        :param listener: The listener to remove.
        :type listener: StateListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_data_listener(self, path: str, listener: DataListener) -> None:
        """
        Add a data listener to a node in zookeeper.

        :param path: The node path.
        :type path: str
        :param listener: The listener to notify when data changed.
        :type listener: DataListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_data_listener(self, listener: DataListener) -> None:
        """
        Remove a data listener from a node in zookeeper.

        :param listener: The listener to remove.
        :type listener: DataListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_children_listener(self, path: str, listener: ChildrenListener) -> None:
        """
        Add a children listener to a node in zookeeper.

        :param path: The node path.
        :type path: str
        :param listener: The listener to notify when children changed.
        :type listener: ChildrenListener
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_children_listener(self, listener: ChildrenListener) -> None:
        """
        Remove a children listener from a node in zookeeper.

        :param listener: The listener to remove.
        :type listener: ChildrenListener
        """
        raise NotImplementedError()


class ZookeeperTransport(abc.ABC):
    @abc.abstractmethod
    def connect(self, url: URL) -> ZookeeperClient:
        """
        Connect to a zookeeper.
        """
        raise NotImplementedError()
