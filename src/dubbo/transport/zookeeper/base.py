# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

import typing
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Self

from dubbo.constants import BACKUP_KEY, CLIENT_KEY, SESSION_KEY
from dubbo.extension import Resource, extension_point, extensions
from dubbo.url import URL

__all__ = ["ZookeeperClient", "get_zookeeper_client"]


@extension_point("apache_dubbo.transport.zookeeper", default="kazoo")
class ZookeeperClient(Resource, typing.Protocol):
    """Read, write and watch the nodes of one ZooKeeper ensemble.

    The implementation is created with a registry or configuration center
    URL and reads only its connection part: the host and port, 2181 if
    absent, then the ``host[:port]`` entries of ``backup``; ``timeout``, to
    connect and for each operation, and ``session``, for the session to
    survive without a connection, in milliseconds, 30000 and 60000 if
    absent; the user and password, which authenticate with digest and make
    the nodes the client creates open only to that user.

    Entering ``async with`` connects within ``timeout``, and closing
    disconnects. Paths are absolute, as in ``/dubbo/config``.

    Operations fail with ``ZookeeperError`` when the ensemble is unreachable,
    times out or refuses them. Missing and existing nodes are not errors;
    each operation states what it does with them.

    Attributes:
        url: The URL the instance was created with.
    """

    url: URL

    def __init__(self, url: URL) -> None:
        self.url = url

    async def get(self, path: str) -> bytes | None:
        """Return the data of the node at ``path``, or ``None`` if it does not exist."""
        ...

    def keep_ephemeral(self, path: str, data: bytes = b"") -> AbstractAsyncContextManager[None]:
        """Keep the ephemeral node at ``path`` with ``data``, creating missing parents, until the context exits.

        Entering creates the node, replacing one that exists, and exiting
        deletes it. Meanwhile the client creates it again in each new
        session, retrying after a delay while it cannot. A later keeper of
        the same path replaces the node and its data, and the earlier one
        then leaves the node on exiting. Entering is all or nothing: one
        that fails deletes what it may have created. An entry or an exit
        that is cancelled returns at once and stops creating the node again,
        but may leave the node to the session, which deletes it as the
        client closes; one after the client has closed has nothing left to
        delete.
        """
        ...

    async def update(self, path: str, change: Callable[[bytes | None], bytes]) -> None:
        """Replace the data of the persistent node at ``path`` with ``change`` of its data.

        ``change`` receives ``None`` while the node does not exist, which is
        then created with its parents. When another client writes the node
        in between, ``change`` runs again on the new data. Data that
        ``change`` returns unchanged is not written. ``change`` may run in
        another thread, so it only computes the new data. A cancelled update
        returns at once, and the write it began may still complete.
        """
        ...

    def watch(self, path: str) -> AbstractAsyncContextManager[AsyncIterator[bytes | None]]:
        """Watch the data of the node at ``path`` until the context exits.

        The iterator yields the current data first, then the data after each
        change, with ``None`` while the node does not exist. Changes made
        while the consumer is busy may be skipped, but the latest is always
        yielded. The watch continues in new sessions. Only entering can
        fail, with ``ZookeeperError``: after it the iterator neither raises
        nor ends until the context exits.
        """
        ...

    def watch_children(self, path: str) -> AbstractAsyncContextManager[AsyncIterator[list[str]]]:
        """Watch the children of ``path`` until the context exits.

        The iterator yields the current names first, then the names after
        each change, with none while the node does not exist; the watch
        follows the node as it is deleted and created again, and continues
        in new sessions. Changes made while the consumer is busy may be
        skipped, but the latest is always yielded. Only entering can fail,
        with ``ZookeeperError``: after it the iterator neither raises nor
        ends until the context exits.
        """
        ...

    async def aclose(self) -> None:
        """Disconnect from the ensemble, which deletes the ephemeral nodes of the client."""
        ...

    async def __aenter__(self) -> Self:
        """Connect to the ensemble within ``timeout``."""
        ...


async def get_zookeeper_client(url: URL) -> ZookeeperClient:
    """Return the client of the ensemble a registry or configuration center URL names, the same for the same connection in its application.

    The ``client`` parameter names the implementation, ``kazoo`` if absent,
    installed with ``apache-dubbo[zookeeper]``. The application of
    ``url.scope`` connects it on first use and disconnects it when it stops.
    URLs that differ only in ``timeout`` share it, with the ``timeout`` of
    the first.

    Raises:
        ValueError: The URL has no host, or a time is not positive whole
            milliseconds.
        ExtensionError: No implementation has the name in ``client``.
        ZookeeperError: The ensemble cannot be reached.
        RuntimeError: ``url`` belongs to no running application.
    """
    if url.host is None:
        raise ValueError(f"a ZooKeeper client needs a host: {url}")

    implementation = extensions.get(ZookeeperClient, url.parameters.get(CLIENT_KEY))
    # shortcut: zk and zk:2181 are two connections; normalize the hosts if that ever matters.
    parameters = url.parameters
    key = (
        implementation,
        url.host,
        url.port,
        parameters.get(BACKUP_KEY),
        url.username,
        url.password,
        parameters.get(SESSION_KEY),
    )
    return await url.scope.share(key, lambda: implementation(url))
