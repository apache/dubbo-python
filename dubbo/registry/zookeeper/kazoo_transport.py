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

from dubbo.common import URL
from dubbo.logger import loggerFactory

from ._interfaces import (
    ChildrenListener,
    DataListener,
    StateListener,
    ZookeeperClient,
    ZookeeperTransport,
)

__all__ = ["KazooZookeeperClient", "KazooZookeeperTransport"]

_LOGGER = loggerFactory.get_logger(__name__)

LISTENER_TYPE = Union[StateListener, DataListener, ChildrenListener]


class AbstractListenerAdapter(abc.ABC):
    """
    Abstract listener adapter.

    This abstract class defines a template for listener adapters, providing thread-safe methods to
    reset and remove listeners. Concrete implementations should provide specific behavior for these methods.
    """

    __slots__ = ["_lock", "_listener"]

    def __init__(self, listener: LISTENER_TYPE):
        """
        Initialize the adapter with a reentrant lock to ensure thread safety.
        :param listener: The listener.
        :type listener: StateListener or DataListener or ChildrenListener
        """
        self._lock = threading.Lock()
        self._listener = listener

    def get_listener(self) -> LISTENER_TYPE:
        """
        Get the listener.
        :return: The listener.
        :rtype:  StateListener or DataListener or ChildrenListener
        """
        return self._listener

    def reset(self, listener: LISTENER_TYPE) -> None:
        """
        Reset with a new listener.

        :param listener: The new listener to set.
        :type listener: StateListener or DataListener or ChildrenListener
        """
        with self._lock:
            self._listener = listener

    def remove(self) -> None:
        """
        Remove the current listener.

        """
        with self._lock:
            self._listener = None


class AbstractListenerAdapterFactory(abc.ABC):
    """
    Abstract factory for creating and managing listener adapters.

    This abstract factory class provides methods to create and remove listener adapters in a
    thread-safe manner. It maintains dictionaries to track active and inactive adapters.
    """

    __slots__ = [
        "_client",
        "_lock",
        "_listener_to_path",
        "_active_adapters",
        "_inactive_adapters",
    ]

    def __init__(self, client: KazooClient):
        """
        Initialize the factory with a KazooClient and set up the necessary locks and dictionaries.

        :param client: An instance of KazooClient to manage Zookeeper connections.
        :type client: KazooClient
        """
        self._client = client
        self._lock = threading.Lock()

        self._listener_to_path = {}
        self._active_adapters: Dict[str, AbstractListenerAdapter] = {}
        self._inactive_adapters: Dict[str, AbstractListenerAdapter] = {}

    def create(self, path: str, listener) -> None:
        """
        Create a new adapter or re-enable an inactive one.

        This method checks if the listener already has an active or inactive adapter. If the adapter is
        inactive, it re-enables it. Otherwise, it creates a new adapter using the abstract `do_create` method.

        :param path: The Znode path to watch.
        :type path: str
        :param listener: The listener for which to create or re-enable an adapter.
        :type listener: Any
        """
        with self._lock:
            adapter = self._active_adapters.pop(path, None)
            if adapter is not None:
                if adapter.get_listener() == listener:
                    return
                else:
                    # replace the listener
                    adapter.reset(listener)
            elif path in self._inactive_adapters:
                # Re-enabling inactive adapter
                adapter = self._inactive_adapters.pop(path)
                adapter.reset(listener)
            else:
                # Creating a new adapter
                adapter = self.do_create(path, listener)

            self._listener_to_path[listener] = path
            self._active_adapters[path] = adapter

    def remove(self, listener) -> None:
        """
        Remove the current listener and move its adapter to the inactive dictionary.

        This method removes the adapter associated with the listener from the active dictionary,
        calls its `remove` method, and then stores it in the inactive dictionary.

        :param listener: The listener whose adapter is to be removed.
        :type listener: Any
        """
        with self._lock:
            path = self._listener_to_path.pop(listener, None)
            if path is None:
                return
            adapter = self._active_adapters.pop(path)
            if adapter is not None:
                adapter.remove()
                self._inactive_adapters[path] = adapter

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

    This adapter inherits from :class:`AbstractListenerAdapter`, but it does not need to use the `reset`
    and `remove` methods. The :class:`KazooClient` provides the `add_listener` and `remove_listener`
    methods, which can effectively replace these methods.

    Note:
        The `add_listener` and `remove_listener` methods of :class:`KazooClient` offer a more efficient
        and straightforward way to manage state listeners, making the `reset` and `remove` methods redundant.
    """

    def __init__(self, listener: StateListener):
        super().__init__(listener)

    def __call__(self, state: KazooState):
        """
        Handle state changes and notify the listener.

        This method is called with the current state of the KazooClient.

        :param state: The current state of the KazooClient.
        :type state: KazooState
        """
        if state == KazooState.CONNECTED:
            state = StateListener.State.CONNECTED
        elif state == KazooState.LOST:
            state = StateListener.State.LOST
        elif state == KazooState.SUSPENDED:
            state = StateListener.State.SUSPENDED

        self._listener.state_changed(state)


class DataListenerAdapter(AbstractListenerAdapter):
    """
    Data listener adapter.

    This adapter handles data change events from a specified Znode path and notifies a `DataListener`.
    It should be used in conjunction with `AbstractListenerAdapterFactory` to manage listener creation
    and removal.
    """

    __slots__ = ["_path"]

    def __init__(self, path: str, listener: DataListener):
        """
        Initialize the KazooDataListenerAdapter with a given path and listener.

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

        This method is called with the current data, stat, and event of the watched Znode.

        :param data: The current data of the Znode.
        :type data: bytes
        :param stat: The status of the Znode.
        :type stat: ZnodeStat
        :param event: The event that triggered the callback.
        :type event: WatchedEvent
        """
        with self._lock:
            if event is None or self._listener is None:
                # This callback is called once immediately after being added, and at this point, event is None.
                # Since a non-existent node also returns None, to avoid handling unknown None exceptions,
                # we directly filter out all cases of None.
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

            self._listener.data_changed(self._path, data, event_type)


class ChildrenListenerAdapter(AbstractListenerAdapter):
    """
    Children listener adapter.

    This adapter handles children change events from a specified Znode path and notifies a `ChildrenListener`.
    It should be used in conjunction with `AbstractListenerAdapterFactory` to manage listener creation and removal.
    """

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

        This method is called with the current list of children of the watched Znode.

        :param children: The current list of children of the Znode.
        :type children: List[str]
        """
        with self._lock:
            if self._listener is not None:
                self._listener.children_changed(self._path, children)


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
        self._client: KazooClient = KazooClient(hosts=url.location)
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

    def create(self, path: str, ephemeral=False) -> None:
        self._client.create(path, ephemeral=ephemeral)

    def create_or_update(self, path: str, data: bytes, ephemeral=False) -> None:
        if self.check_exist(path):
            self._client.set(path, data)
        else:
            self._client.create(path, data, ephemeral=ephemeral)

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
