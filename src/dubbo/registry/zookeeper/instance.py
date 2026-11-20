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

import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Self

import anyio
from anyio.abc import TaskStatus

from dubbo.constants import GROUP_KEY
from dubbo.transport import zookeeper
from dubbo.url import URL
from dubbo.utils import Latest, create_background_task_group, follow

from ..base import InstanceRegistry, ServiceInstance

__all__ = ["ZookeeperInstanceRegistry"]

_logger = logging.getLogger(__name__)

_INSTANCES_ROOT = "/services"
_ROOT_PATH_KEY = "rootPath"
# The class name the Curator instance payload carries.
_PAYLOAD_CLASS = "org.apache.dubbo.registry.zookeeper.ZookeeperInstance"


class ZookeeperInstanceRegistry(InstanceRegistry):
    """An ``InstanceRegistry`` in ZooKeeper nodes holding Curator service-instance JSON.

    An instance is the ephemeral node ``{root}/{application}/{host}:{port}``
    holding the JSON of an Apache Curator service instance. The root is the
    ``rootPath`` URL parameter, else ``/`` and the ``group`` parameter, else
    ``/services``. The client comes from ``get_zookeeper_client``, shared
    with the other users of an equal connection.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._root = _instances_root(url)
        self._client: zookeeper.ZookeeperClient | None = None

    def register(self, instance: ServiceInstance) -> AbstractAsyncContextManager[None]:
        client = self._connected()

        return client.keep_ephemeral(self._path(instance.app, instance.id), _json(instance))

    @asynccontextmanager
    async def subscribe(self, app: str) -> AsyncGenerator[AsyncIterator[list[ServiceInstance]]]:
        client = self._connected()
        parent = self._path(app)
        latest: Latest[list[ServiceInstance]] = Latest()
        instances: dict[str, ServiceInstance] = {}
        watches: dict[str, anyio.CancelScope] = {}
        subscribed = False

        def update(child: str, data: bytes | None) -> None:
            instance = _instance(data, f"{parent}/{child}")
            if instance is None:
                instances.pop(child, None)
            else:
                instances[child] = instance

        def publish() -> None:
            if subscribed:
                latest.publish(list(instances.values()))

        async def watch_instance(
            child: str, scope: anyio.CancelScope, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED
        ) -> None:
            async def receive(data: bytes | None) -> None:
                # The watch of an instance that left and came back is replaced, and updates nothing.
                if watches.get(child) is scope:
                    update(child, data)
                    publish()

            path = f"{parent}/{child}"
            with scope:
                # Only the instances of the first snapshot fail the subscription; a later one is watched again.
                await follow(lambda: client.watch(path), receive, path, retry_first=subscribed, task_status=task_status)

        async def follow_children(children: list[str]) -> None:
            for child in watches.keys() - set(children):
                watches.pop(child).cancel()
                instances.pop(child, None)
            for child in sorted(set(children) - watches.keys()):
                scope = watches[child] = anyio.CancelScope()
                if subscribed:
                    task_group.start_soon(watch_instance, child, scope)
                else:
                    await task_group.start(watch_instance, child, scope)

            publish()

        async def watch_children(*, task_status: TaskStatus[None]) -> None:
            nonlocal subscribed
            async with client.watch_children(parent) as snapshots:
                await follow_children(await anext(snapshots))
                subscribed = True
                publish()
                task_status.started()
                async for children in snapshots:
                    await follow_children(children)

        async with create_background_task_group() as task_group:
            await task_group.start(watch_children)
            try:
                yield aiter(latest)
            finally:
                task_group.cancel_scope.cancel()

    async def aclose(self) -> None:
        self._client = None

    async def __aenter__(self) -> Self:
        self._client = await zookeeper.get_zookeeper_client(self.url)
        return self

    def _path(self, *names: str) -> str:
        return "/".join((self._root, *names))

    def _connected(self) -> zookeeper.ZookeeperClient:
        if self._client is None:
            raise RuntimeError("the registry is not connected")
        return self._client


def _instances_root(url: URL) -> str:
    root = url.parameters.get(_ROOT_PATH_KEY, _INSTANCES_ROOT)
    if root.lower() == _INSTANCES_ROOT:
        root = url.parameters.get(GROUP_KEY, _INSTANCES_ROOT)
    return "/" + root.strip("/")


def _json(instance: ServiceInstance) -> bytes:
    payload = {
        "@class": _PAYLOAD_CLASS,
        "id": instance.id,
        "name": instance.app,
        "metadata": dict(instance.metadata),
    }
    data = {
        "name": instance.app,
        "id": instance.id,
        "address": instance.host,
        "port": instance.port,
        "sslPort": None,
        "payload": payload,
        "registrationTimeUTC": time.time_ns() // 1_000_000,
        "serviceType": "DYNAMIC",
        "uriSpec": None,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


def _instance(data: bytes | None, path: str) -> ServiceInstance | None:
    """Read the instance in ``data``, or return ``None`` when the node is gone or holds no instance."""
    if not data:
        return None

    try:
        node: Mapping[str, Any] = json.loads(data)
        payload = node.get("payload") or {}
        metadata = payload.get("metadata") or {}
        return ServiceInstance(
            app=str(node["name"]),
            host=str(node["address"]),
            port=int(node["port"]),
            metadata={str(key): str(value) for key, value in metadata.items()},
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        _logger.warning("Ignoring the service instance in %s, which cannot be read", path, exc_info=True)
        return None
