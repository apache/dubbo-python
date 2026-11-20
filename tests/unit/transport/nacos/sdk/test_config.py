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

import anyio
import attrs
import pytest
from v2.nacos import ConfigParam, NacosException

from dubbo.transport.nacos import NacosError
from dubbo.transport.nacos.sdk import SdkNacosConfigClient
from dubbo.transport.nacos.sdk import config as sdk_config
from dubbo.url import URL

pytestmark = pytest.mark.anyio


@attrs.define(kw_only=False)
class _Configs:
    """A configuration service of the SDK that another writer changes once while it is read."""

    content: str | tuple[str, str]
    interference: str | None = None
    published: list[tuple[str, str, str, str]] = attrs.field(factory=list)

    @property
    def grpc_client_proxy(self):
        return self

    async def start(self):
        pass

    async def shutdown(self):
        pass

    async def get_config(self, param: ConfigParam) -> str | tuple[str, str]:
        return self.content

    async def publish_config(self, param: ConfigParam) -> bool:
        self.published.append((param.data_id, param.group, param.content, param.cas_md5))
        if self.interference is not None:
            self.content, self.interference = self.interference, None
            raise NacosException(400, "md5 does not match")
        self.content = param.content
        return True


@pytest.mark.parametrize(("current", "md5"), [("", "0"), ("a", hashlib.md5(b"a").hexdigest())])
async def test_sdk_writes_a_configuration_if_it_is_still_what_was_read(monkeypatch, current, md5):
    configs = _Configs(content=current)
    monkeypatch.setattr(sdk_config, "NacosConfigService", lambda settings: configs)

    async with SdkNacosConfigClient(URL.parse("nacos://n")) as client:
        await client.update("d", "g", lambda content: (content or "") + "b")

    assert configs.published == [("d", "g", current + "b", md5)]


async def test_sdk_reads_the_local_cache_it_falls_back_to_as_the_configuration(monkeypatch):
    configs = _Configs(content=("a", ""))
    monkeypatch.setattr(sdk_config, "NacosConfigService", lambda settings: configs)

    async with SdkNacosConfigClient(URL.parse("nacos://n")) as client:
        assert await client.get("d", "g") == "a"


async def test_sdk_fails_a_read_whose_fallback_finds_no_local_cache(monkeypatch):
    configs = _Configs(content=("", ""))
    monkeypatch.setattr(sdk_config, "NacosConfigService", lambda settings: configs)

    async with SdkNacosConfigClient(URL.parse("nacos://n")) as client:
        with pytest.raises(NacosError, match="cannot read d"):
            await client.get("d", "g")


async def test_sdk_reads_a_configuration_again_that_changed_before_it_was_written(monkeypatch):
    configs = _Configs(content="a", interference="a,c")
    monkeypatch.setattr(sdk_config, "NacosConfigService", lambda settings: configs)
    monkeypatch.setattr(sdk_config, "_CAS_WAIT", 0)

    async with SdkNacosConfigClient(URL.parse("nacos://n")) as client:
        await client.update("d", "g", lambda content: f"{content},b")

    assert configs.content == "a,c,b"
    assert configs.published == [
        ("d", "g", "a,b", hashlib.md5(b"a").hexdigest()),
        ("d", "g", "a,c,b", hashlib.md5(b"a,c").hexdigest()),
    ]


async def test_sdk_watch_cancelled_while_adding_its_listener_leaves_none(monkeypatch):
    class Configs:
        def __init__(self):
            self.grpc_client_proxy = self
            self.listeners = []

        async def start(self):
            pass

        async def shutdown(self):
            pass

        async def add_listener(self, data_id, group, listener):
            self.listeners.append(listener)
            await anyio.sleep_forever()

        async def remove_listener(self, data_id, group, listener):
            self.listeners.remove(listener)

    configs = Configs()
    monkeypatch.setattr(sdk_config, "NacosConfigService", lambda settings: configs)

    async with SdkNacosConfigClient(URL.parse("nacos://n")) as client:
        with anyio.move_on_after(0.1):
            async with client.watch("d", "g"):
                pytest.fail("the watch was not cancelled")

    assert configs.listeners == []
