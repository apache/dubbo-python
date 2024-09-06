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
import threading
from typing import Dict, List, Union

from kazoo.client import KazooClient
from kazoo.protocol.states import EventType, KazooState, WatchedEvent, ZnodeStat

from dubbo.loggers import loggerFactory
from dubbo.url import URL

from ._interfaces import (
    ChildrenListener,
    DataListener,
    StateListener,
    ZookeeperClient,
    ZookeeperTransport,
)

__all__ = ["KazooZookeeperClient", "KazooZookeeperTransport"]

_LOGGER = loggerFactory.get_logger("zookeeper")

LISTENER_TYPE = Union[StateListener, DataListener, ChildrenListener]


class AbstractListenerAdapter(abc.ABC):
    """
    Abstract listener adapter.

    This abstract class defines a template for listener adapters, providing thread-safe methods to
    manage listeners. Concrete implementations should provide specific behavior for these methods.
    """

    __slots__ = ["_lock", "_listeners"]

    def __init__(self, listener: LISTENER_TYPE):
        """
        Initialize the adapter with a reentrant lock to ensure thread safety and store the initial listener.

        :param listener: The listener to manage.
        :type listener: StateListener or DataListener or ChildrenListener
        """
        self._lock = threading.Lock()
        self._listeners = {listener}

    def add(self, listener: LISTENER_TYPE) -> None:
        """
        Add a listener to the adapter.

        This method adds a listener to the adapter's set of listeners in a thread-safe manner.

        :param listener: The listener to add.
        :type listener: StateListener or DataListener or ChildrenListener
        """
        with self._lock:
            self._listeners.add(listener)

    def remove(self, listener: LISTENER_TYPE) -> None:
        """
        Remove a listener from the adapter.

        This method removes a listener from the adapter's set of listeners in a thread-safe manner.

        :param listener: The listener to remove.
        :type listener: StateListener or DataListener or ChildrenListener
        """
        with self._lock:
            self._listeners.remove(listener)


class AbstractListenerAdapterFactory(abc.ABC):
    """
    Abstract factory for creating and managing listener adapters.

    This abstract factory class provides methods to create and manage listener adapters
    in a thread-safe manner. It maintains a dictionary to track active adapters.
    """

    __slots__ = [
        "_client",
        "_lock",
        "_adapters",
        "_listener_to_path",
    ]

    def __init__(self, client: KazooClient):
        """
        Initialize the factory with a KazooClient and set up the necessary locks and dictionaries.

        :param client: An instance of KazooClient to manage Zookeeper connections.
        :type client: KazooClient
        """
        self._client = client
        self._lock = threading.Lock()
        self._adapters: Dict[str, AbstractListenerAdapter] = {}
        self._listener_to_path: Dict[LISTENER_TYPE, str] = {}

    def create(self, path: str, listener) -> None:
        """
        Create a new adapter or add a listener to an existing adapter.

        This method checks if the specified path already has an adapter. If so, it adds the listener
        to the existing adapter. Otherwise, it creates a new adapter using the abstract `do_create` method.

        :param path: The Znode path to watch.
        :type path: str
        :param listener: The listener for which to create or add to an adapter.
        :type listener: Any
        """
        with self._lock:
            adapter = self._adapters.get(path)
            if not adapter:
                # Creating a new adapter
                adapter = self.do_create(path, listener)
                self._adapters[path] = adapter
            else:
                # Add the listener to the adapter
                adapter.add(listener)

    def remove(self, listener) -> None:
        """
        Remove a listener and its associated adapter if no listeners remain.

        This method removes the listener's adapter from the active adapters dictionary and
        removes the listener from the adapter. If no listeners remain, the adapter is discarded.

        :param listener: The listener to remove.
        :type listener: Any
        """
        with self._lock:
            path = self._listener_to_path.pop(listener, None)
            if path is None:
                return
            adapter = self._adapters.get(path)
            if adapter is not None:
                adapter.remove(listener)

    @abc.abstractmethod
    def do_create(self, path: str, listener) -> AbstractListenerAdapter:
        """
        Define the creation of a new adapter.

        This abstract method must be implemented by subclasses to handle the actual creation logic
        for a new adapter.

        :param path: The Znode path to watch.
        :type path: str
        :param listener: The listener for which to create a new adapter.
        :type listener: Any
        :return: A new instance of an AbstractListenerAdapter.
        :rtype: AbstractListenerAdapter
        :raises NotImplementedError: If the method is not implemented by a subclass.
        """
        raise NotImplementedError()


class StateListenerAdapter(AbstractListenerAdapter):
    """
    State listener adapter.

    This adapter inherits from `AbstractListenerAdapter` and is designed to handle state changes
    in a `KazooClient`. It converts Zookeeper states to internal states and notifies listeners.
    """

    def __init__(self, listener: StateListener):
        """
        Initialize the StateListenerAdapter with a given listener.

        :param listener: The listener to manage.
        :type listener: StateListener
        """
        super().__init__(listener)

    def __call__(self, state: KazooState):
        """
        Handle state changes and notify the listener.

        This method is called with the current state of the KazooClient, converts it to an internal
        state representation, and notifies all registered listeners.

        :param state: The current state of the KazooClient.
        :type state: KazooState
        """
        if state == KazooState.CONNECTED:
            state = StateListener.State.CONNECTED
        elif state == KazooState.LOST:
            state = StateListener.State.LOST
        elif state == KazooState.SUSPENDED:
            state = StateListener.State.SUSPENDED

        # Notify all listeners
        for listener in self._listeners:
            listener.state_changed(state)


class DataListenerAdapter(AbstractListenerAdapter):
    """
    Data listener adapter.

    This adapter handles data change events for a specified Znode path and notifies a `DataListener`.
    """

    __slots__ = ["_path"]

    def __init__(self, path: str, listener: DataListener):
        """
        Initialize the DataListenerAdapter with a given path and listener.

        :param path: The Znode path to watch.
        :type path: str
        :param listener: The data listener to notify on data changes.
        :type listener: DataListener
        """
        super().__init__(listener)
        self._path = path

    def __call__(self, data: bytes, stat: ZnodeStat, event: WatchedEvent):
        """
        Handle data changes and notify the listener.

        This method is called with the current data, stat, and event of the watched Znode,
        processes the event type, and notifies all registered listeners.

        :param data: The current data of the Znode.
        :type data: bytes
        :param stat: The status of the Znode.
        :type stat: ZnodeStat
        :param event: The event that triggered the callback.
        :type event: WatchedEvent
        """
        with self._lock:
            if event is None or len(self._listeners) == 0:
                return

            event_type = None
            if event.type == EventType.NONE:
                event_type = DataListener.EventType.NONE
            elif event.type == EventType.CREATED:
                event_type = DataListener.EventType.CREATED
            elif event.type == EventType.DELETED:
                event_type = DataListener.EventType.DELETED
            elif event.type == EventType.CHANGED:
                event_type = DataListener.EventType.CHANGED
            elif event.type == EventType.CHILD:
                event_type = DataListener.EventType.CHILD

            # Notify all listeners
            for listener in self._listeners:
                listener.data_changed(self._path, data, event_type)


class ChildrenListenerAdapter(AbstractListenerAdapter):
    """
    Children listener adapter.

    This adapter handles children change events for a specified Znode path and notifies a `ChildrenListener`.
    """

    __slots__ = ["_path"]

    def __init__(self, path: str, listener: ChildrenListener):
        """
        Initialize the ChildrenListenerAdapter with a given path and listener.

        :param path: The Znode path to watch.
        :type path: str
        :param listener: The children listener to notify on children changes.
        :type listener: ChildrenListener
        """
        super().__init__(listener)
        self._path = path

    def __call__(self, children: List[str]):
        """
        Handle children changes and notify the listener.

        This method is called with the current list of children of the watched Znode
        and notifies all registered listeners.

        :param children: The current list of children of the Znode.
        :type children: List[str]
        """
        with self._lock:
            # Notify all listeners
            for listener in self._listeners:
                listener.children_changed(self._path, children)


class DataListenerAdapterFactory(AbstractListenerAdapterFactory):
    def do_create(self, path: str, listener: DataListener) -> AbstractListenerAdapter:
        data_adapter = DataListenerAdapter(path, listener)
        self._client.DataWatch(path, data_adapter)
        return data_adapter


class ChildrenListenerAdapterFactory(AbstractListenerAdapterFactory):
    def do_create(
        self, path: str, listener: ChildrenListener
    ) -> AbstractListenerAdapter:
        children_adapter = ChildrenListenerAdapter(path, listener)
        self._client.ChildrenWatch(path, children_adapter)
        return children_adapter


class KazooZookeeperClient(ZookeeperClient):
    """
    Kazoo Zookeeper client.
    """

    def __init__(self, url: URL):
        super().__init__(url)
        self._client: KazooClient = KazooClient(hosts=url.location, logger=_LOGGER)
        # TODO: Add more attributes from url

        # state listener dict
        self._state_lock = threading.Lock()
        self._state_listeners: Dict[StateListener, StateListenerAdapter] = {}

        self._data_adapter_factory = DataListenerAdapterFactory(self._client)

        self._children_adapter_factory = ChildrenListenerAdapterFactory(self._client)

    def start(self) -> None:
        # start the client
        self._client.start()

    def stop(self) -> None:
        # stop the client
        self._client.stop()

    def is_connected(self) -> bool:
        return self._client.connected

    def create(self, path: str, data: bytes = b"", ephemeral=False) -> None:
        self._client.create(path, data, ephemeral=ephemeral, makepath=True)

    def create_or_update(self, path: str, data: bytes, ephemeral=False) -> None:
        if self.check_exist(path):
            self._client.set(path, data)
        else:
            self.create(path, data, ephemeral=ephemeral)

    def check_exist(self, path: str) -> bool:
        return self._client.exists(path)

    def get_data(self, path: str) -> bytes:
        # data: bytes, stat: ZnodeStat
        data, stat = self._client.get(path)
        return data

    def get_children(self, path: str) -> list:
        return self._client.get_children(path)

    def delete(self, path: str) -> None:
        self._client.delete(path)

    def add_state_listener(self, listener: StateListener) -> None:
        with self._state_lock:
            if listener in self._state_listeners:
                return
            state_adapter = StateListenerAdapter(listener)
            self._client.add_listener(state_adapter)
            self._state_listeners[listener] = state_adapter

    def remove_state_listener(self, listener: StateListener) -> None:
        with self._state_lock:
            state_adapter = self._state_listeners.pop(listener, None)
            if state_adapter is not None:
                self._client.remove_listener(state_adapter)

    def add_data_listener(self, path: str, listener: DataListener) -> None:
        self._data_adapter_factory.create(path, listener)

    def remove_data_listener(self, listener: DataListener) -> None:
        self._data_adapter_factory.remove(listener)

    def add_children_listener(self, path: str, listener: ChildrenListener) -> None:
        self._children_adapter_factory.create(path, listener)

    def remove_children_listener(self, listener: ChildrenListener) -> None:
        self._children_adapter_factory.remove(listener)


class KazooZookeeperTransport(ZookeeperTransport):
    def __init__(self):
        self._lock = threading.Lock()
        # key: location, value: KazooZookeeperClient
        self._zk_client_dict: Dict[str, KazooZookeeperClient] = {}

    def connect(self, url: URL) -> ZookeeperClient:
        with self._lock:
            zk_client = self._zk_client_dict.get(url.location)
            if zk_client is None or zk_client.is_connected():
                # Create new KazooZookeeperClient
                zk_client = KazooZookeeperClient(url)
                zk_client.start()
                self._zk_client_dict[url.location] = zk_client

            return zk_client
