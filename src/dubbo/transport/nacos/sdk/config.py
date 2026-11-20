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

import hashlib
import random
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Self

import anyio

from dubbo.url import URL
from dubbo.utils import Latest, require_optional_dependency

from ..base import NacosConfigClient
from ..exceptions import NacosError
from .connection import call, client_config, release

with require_optional_dependency("v2.nacos", extra="nacos"):
    from v2.nacos import ConfigParam, NacosConfigService, NacosException

__all__ = ["SdkNacosConfigClient"]


# A compare-and-set is tried 10 times, waiting up to 100 ms at random in between.
_CAS_TRIES = 10
_CAS_WAIT = 0.1  # Seconds.
# The compare-and-set MD5 that stands for a configuration that does not exist.
_MISSING_MD5 = "0"


class SdkNacosConfigClient(NacosConfigClient):
    """A ``NacosConfigClient`` backed by the configuration service of nacos-sdk-python, the official client.

    The SDK reconnects by itself, and then watches again.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)
        self._settings = client_config(url)
        self._config: NacosConfigService | None = None

    async def get(self, data_id: str, group: str) -> str | None:
        config = self._connected()

        return await self._read(config, _name(data_id), _name(group))

    async def update(self, data_id: str, group: str, change: Callable[[str | None], str]) -> None:
        config = self._connected()
        data_id, group = _name(data_id), _name(group)

        for tries_left in reversed(range(_CAS_TRIES)):
            current = await self._read(config, data_id, group)
            content = change(current)
            if content == current:
                return

            expected = hashlib.md5(current.encode()).hexdigest() if current else _MISSING_MD5
            param = ConfigParam(data_id=data_id, group=group, content=content, cas_md5=expected)
            try:
                if await config.publish_config(param):
                    return
            except NacosException as error:
                if not tries_left:
                    raise NacosError(f"cannot write {data_id}: {error}") from error
            await anyio.sleep(random.uniform(0, _CAS_WAIT))

        raise NacosError(f"cannot write {data_id}: it kept changing")

    @asynccontextmanager
    async def watch(self, data_id: str, group: str) -> AsyncGenerator[AsyncIterator[str | None]]:
        config = self._connected()
        latest: Latest[str | None] = Latest()

        async def changed(_tenant: str, _group: str, _data_id: str, content: str | None) -> None:
            latest.publish(content or None)

        data_id, group = _name(data_id), _name(group)
        try:
            await call(config.add_listener(data_id, group, changed), f"watch {data_id}")
            # The SDK calls back only on a change.
            latest.publish(await self._read(config, data_id, group))
            yield aiter(latest)
        finally:
            await release(config.remove_listener(data_id, group, changed), f"stop watching {data_id} in Nacos")

    async def aclose(self) -> None:
        config, self._config = self._config, None
        if config is not None:
            await release(_shut_down(config), f"disconnect from Nacos at {self.url.address} cleanly")

    async def __aenter__(self) -> Self:
        # The service, whose tasks run from the start, is kept before connecting, so that a start that fails or
        # is cancelled shuts them down.
        config = NacosConfigService(self._settings)
        try:
            await call(config.grpc_client_proxy.start(), f"connect to Nacos at {self.url.address}")
        except BaseException:
            await release(_shut_down(config), f"disconnect from Nacos at {self.url.address} cleanly")
            raise

        self._config = config
        return self

    def _connected(self) -> NacosConfigService:
        if self._config is None:
            raise RuntimeError("the Nacos configuration client is not connected")
        return self._config

    @staticmethod
    async def _read(config: NacosConfigService, data_id: str, group: str) -> str | None:
        content = await call(config.get_config(ConfigParam(data_id=data_id, group=group)), f"read {data_id}")
        # nacos-sdk-python 3.2.0 answers a failed read with the (content, key) pair of its local cache.
        if isinstance(content, tuple):
            content = content[0]
            if not content:
                raise NacosError(f"cannot read {data_id}: the server failed and the local cache holds nothing")

        # The SDK returns an empty text for a configuration that does not exist, which Nacos never stores.
        return content or None


def _name(name: str) -> str:
    return name.replace("$", "___").replace("/", "-")


async def _shut_down(service: NacosConfigService) -> None:
    # nacos-sdk-python 3.2.0 stops its listen task by a flag it reads every five seconds, and waits for it; the task
    # ends at once when cancelled.
    service.grpc_client_proxy.listen_task.cancel()
    await service.shutdown()
