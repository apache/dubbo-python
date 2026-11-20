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

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Self

import anyio

from dubbo.url import URL
from dubbo.utils import Latest, require_optional_dependency

from ..base import NacosInstance, NacosNamingClient
from ..exceptions import NacosError
from .connection import call, client_config, release

with require_optional_dependency("v2.nacos", extra="nacos"):
    from v2.nacos import (
        BatchRegisterInstanceParam,
        DeregisterInstanceParam,
        Instance,
        ListInstanceParam,
        NacosNamingService,
        RegisterInstanceParam,
        SubscribeServiceParam,
    )

__all__ = ["SdkNacosNamingClient"]


class SdkNacosNamingClient(NacosNamingClient):
    """A ``NacosNamingClient`` backed by the naming service of nacos-sdk-python, the official client.

    The SDK reconnects by itself, and then registers its instances and
    watches again. Nacos keeps one registration of a service for each
    connection, which a later one replaces, so the instances of a service at
    several addresses register together. An instance kept again at its
    address, as with other metadata, replaces the one there, whose keeper
    then leaves it on exiting.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._config = client_config(url)
        self._naming: NacosNamingService | None = None
        # The instances registered of each service and group, by host and port, and the keeper of each.
        self._registered: dict[tuple[str, str], dict[tuple[str, int], RegisterInstanceParam]] = {}
        self._keepers: dict[tuple[tuple[str, str], tuple[str, int]], object] = {}
        self._registering = anyio.Lock()

    @asynccontextmanager
    async def keep_registered(self, service: str, group: str, instance: NacosInstance) -> AsyncGenerator[None]:
        key = (_name(service), _name(group))
        address = (instance.host, instance.port)
        keeper = object()

        await self._register(key, service, instance)
        self._keepers[key, address] = keeper
        try:
            yield
        finally:
            # Taken before deregistering, so that a cancelled exit still leaves the instance to the connection.
            if self._keepers.get((key, address)) is keeper:
                del self._keepers[key, address]
                await self._deregister(key, service, instance)

    @asynccontextmanager
    async def watch(self, service: str, group: str) -> AsyncGenerator[AsyncIterator[list[NacosInstance]]]:
        naming = self._connected()
        latest: Latest[list[NacosInstance]] = Latest()

        async def changed(instances: list[Instance] | None) -> None:
            latest.publish(_instances(instances))

        service_name, group_name = _name(service), _name(group)
        param = SubscribeServiceParam(service_name=service_name, group_name=group_name, subscribe_callback=changed)
        try:
            await call(naming.subscribe(param), f"watch {service}")
            # The SDK calls back only on a change, which a service already watched may not have.
            listed = ListInstanceParam(service_name=service_name, group_name=group_name, healthy_only=None)
            latest.publish(_instances(await call(naming.list_instances(listed), f"list {service}")))
            yield aiter(latest)
        finally:
            await release(naming.unsubscribe(param), f"stop watching {service} in Nacos")

    async def aclose(self) -> None:
        naming, self._naming = self._naming, None
        self._registered = {}
        self._keepers = {}
        if naming is not None:
            await release(_shut_down(naming), f"disconnect from Nacos at {self.url.address} cleanly")

    async def __aenter__(self) -> Self:
        # The service is kept before connecting, so that a start that fails or is cancelled shuts it down.
        naming = NacosNamingService(self._config)
        try:
            await call(naming.grpc_client_proxy.start(), f"connect to Nacos at {self.url.address}")
        except BaseException:
            await release(_shut_down(naming), f"disconnect from Nacos at {self.url.address} cleanly")
            raise

        self._naming = naming
        return self

    async def _register(self, key: tuple[str, str], service: str, instance: NacosInstance) -> None:
        naming = self._connected()
        param = RegisterInstanceParam(
            ip=instance.host,
            port=instance.port,
            metadata=dict(instance.metadata),
            service_name=key[0],
            group_name=key[1],
        )
        action = f"register {instance.host}:{instance.port} in {service}"

        async with self._registering:
            before = self._registered.get(key, {})
            instances = {**before, (instance.host, instance.port): param}
            try:
                if len(instances) == 1:
                    registered = await call(naming.register_instance(param), action)
                else:
                    registered = await call(naming.batch_register_instances(_batch(key, instances)), action)
                if not registered:
                    raise NacosError(f"cannot {action}: the server refused it")
            except BaseException:
                # The server may hold the instance: it holds again what it held before, as far as it can.
                await release(self._replace(naming, key, before, instance, action), f"undo the attempt to {action}")
                raise
            self._registered[key] = instances

    async def _deregister(self, key: tuple[str, str], service: str, instance: NacosInstance) -> None:
        naming = self._connected()
        action = f"deregister {instance.host}:{instance.port} from {service}"

        async with self._registering:
            instances = dict(self._registered.get(key, {}))
            instances.pop((instance.host, instance.port), None)
            await self._replace(naming, key, instances, instance, action)

    async def _replace(
        self,
        naming: NacosNamingService,
        key: tuple[str, str],
        instances: dict[tuple[str, int], RegisterInstanceParam],
        instance: NacosInstance,
        action: str,
    ) -> None:
        """Make the server hold ``instances`` of the service ``key``, registered together, or none, ``instance`` deregistered."""
        if not instances:
            param = DeregisterInstanceParam(
                ip=instance.host, port=instance.port, service_name=key[0], group_name=key[1]
            )
            await call(naming.deregister_instance(param), action)
            self._registered.pop(key, None)
            return

        if not await call(naming.batch_register_instances(_batch(key, instances)), action):
            raise NacosError(f"cannot {action}: the server refused it")
        self._registered[key] = instances

    def _connected(self) -> NacosNamingService:
        if self._naming is None:
            raise RuntimeError("the Nacos naming client is not connected")
        return self._naming


def _name(name: str) -> str:
    return name.replace("$", "___")


def _batch(key: tuple[str, str], instances: dict[tuple[str, int], RegisterInstanceParam]) -> BatchRegisterInstanceParam:
    service_name, group_name = key
    return BatchRegisterInstanceParam(
        service_name=service_name, group_name=group_name, instances=list(instances.values())
    )


def _instances(instances: Iterable[Instance] | None) -> list[NacosInstance]:
    return [
        NacosInstance(
            host=instance.ip,
            port=instance.port,
            metadata={str(key): str(value) for key, value in (instance.metadata or {}).items()},
        )
        for instance in instances or ()
        if instance.healthy and instance.enabled
    ]


async def _shut_down(naming: NacosNamingService) -> None:
    try:
        await naming.shutdown()
    finally:
        # nacos-sdk-python 3.2.0 leaves the task of the redo service running after shutdown; it ends when cancelled.
        task = naming.grpc_client_proxy.redo_service._listen_task
        task.cancel()
        await asyncio.wait((task,))
