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

from contextlib import asynccontextmanager

import anyio
import pytest

import dubbo.registry.discovery as discovery
from dubbo.extension import ApplicationScope, Resource, extensions
from dubbo.metadata import MetadataInfo, MetadataReport, ServiceInfo
from dubbo.registry import InstanceRegistry, ServiceInstance
from dubbo.registry.discovery import subscribe_by_instance
from dubbo.url import APPLICATION_SCOPE, URL
from dubbo.utils import Latest

pytestmark = pytest.mark.anyio


async def test_an_unreadable_revision_is_read_again_without_watching_the_registry_again(
    isolated_extensions, monkeypatch
):
    monkeypatch.setattr(discovery, "backoff", lambda: iter([0.01] * 1000))
    info = MetadataInfo.from_services(
        "demo", [ServiceInfo(name="test.Greeter", protocol="tri", port=50051, path="test.Greeter")]
    )
    snapshots = Latest()
    subscriptions = 0
    failures = 0

    def instance(revision, host="10.0.0.5"):
        return ServiceInstance(
            app="demo",
            host=host,
            port=50051,
            metadata={"dubbo.metadata.revision": revision, "dubbo.metadata.storage-type": "remote"},
        )

    class Instances(Resource):
        @asynccontextmanager
        async def subscribe(self, app):
            nonlocal subscriptions
            subscriptions += 1
            yield aiter(snapshots)

        async def aclose(self):
            pass

    class Report(Resource):
        async def get_app_metadata(self, app, revision):
            nonlocal failures
            if revision != info.revision:
                failures += 1
                raise OSError("unreachable")
            return info

        async def aclose(self):
            pass

    extensions.register(InstanceRegistry, "memory", lambda url: Instances())
    extensions.register(MetadataReport, "memory", lambda url: Report())
    snapshots.publish([instance(info.revision), instance("new", host="10.0.0.6")])
    seen = []

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            url = URL.parse("memory://registry").replace(attributes={APPLICATION_SCOPE: scope})
            async with subscribe_by_instance(url, "test.Greeter", ["demo"]) as urls, anyio.create_task_group() as tasks:

                async def collect():
                    async for each in urls:
                        seen.append(each)  # noqa: PERF401 - the iteration never ends, so each value is kept as it comes

                tasks.start_soon(collect)
                while failures < 5:
                    await anyio.sleep(0.01)
                tasks.cancel_scope.cancel()

    # Each retry reads the unreadable revision again; the instance with the readable one keeps its URLs throughout.
    assert subscriptions == 1
    assert seen
    assert all(each == [URL.parse("tri://10.0.0.5:50051/test.Greeter")] for each in seen)


async def test_an_unreadable_new_revision_keeps_the_last_urls_until_the_instance_leaves(isolated_extensions):
    info = MetadataInfo.from_services(
        "demo", [ServiceInfo(name="test.Greeter", protocol="tri", port=50051, path="test.Greeter")]
    )
    failed = anyio.Event()
    snapshots = Latest()

    def instance(revision):
        return ServiceInstance(
            app="demo",
            host="10.0.0.5",
            port=50051,
            metadata={"dubbo.metadata.revision": revision, "dubbo.metadata.storage-type": "remote"},
        )

    class Instances(Resource):
        @asynccontextmanager
        async def subscribe(self, app):
            yield aiter(snapshots)

        async def aclose(self):
            pass

    class Report(Resource):
        async def get_app_metadata(self, app, revision):
            if revision != info.revision:
                failed.set()
                raise OSError("unreachable")
            return info

        async def aclose(self):
            pass

    extensions.register(InstanceRegistry, "memory", lambda url: Instances())
    extensions.register(MetadataReport, "memory", lambda url: Report())
    snapshots.publish([instance(info.revision)])

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            url = URL.parse("memory://registry").replace(attributes={APPLICATION_SCOPE: scope})
            async with subscribe_by_instance(url, "test.Greeter", ["demo"]) as urls:
                assert await anext(urls) == [URL.parse("tri://10.0.0.5:50051/test.Greeter")]

                snapshots.publish([instance("new")])
                await failed.wait()
                assert await anext(urls) == [URL.parse("tri://10.0.0.5:50051/test.Greeter")]

                snapshots.publish([])
                assert await anext(urls) == []


async def test_an_instance_that_does_not_change_keeps_the_same_urls_when_another_is_replaced(isolated_extensions):
    info = MetadataInfo.from_services(
        "demo", [ServiceInfo(name="test.Greeter", protocol="tri", port=50051, path="test.Greeter")]
    )
    snapshots = Latest()

    def instance(host):
        return ServiceInstance(
            app="demo",
            host=host,
            port=50051,
            metadata={"dubbo.metadata.revision": info.revision, "dubbo.metadata.storage-type": "remote"},
        )

    class Instances(Resource):
        @asynccontextmanager
        async def subscribe(self, app):
            yield aiter(snapshots)

        async def aclose(self):
            pass

    class Report(Resource):
        async def get_app_metadata(self, app, revision):
            return info

        async def aclose(self):
            pass

    extensions.register(InstanceRegistry, "memory", lambda url: Instances())
    extensions.register(MetadataReport, "memory", lambda url: Report())
    snapshots.publish([instance("10.0.0.5"), instance("10.0.0.6")])

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            url = URL.parse("memory://registry").replace(attributes={APPLICATION_SCOPE: scope})
            async with subscribe_by_instance(url, "test.Greeter", ["demo"]) as urls:
                kept, _ = await anext(urls)
                snapshots.publish([instance("10.0.0.5"), instance("10.0.0.7")])
                after = await anext(urls)

    assert after == [kept, URL.parse("tri://10.0.0.7:50051/test.Greeter")]
    assert after[0] is kept


async def test_an_instance_whose_metadata_holds_no_valid_url_leaves_the_others_of_its_application(
    isolated_extensions,
):
    good = MetadataInfo.from_services(
        "demo", [ServiceInfo(name="test.Greeter", protocol="tri", port=50051, path="test.Greeter")]
    )
    bad = MetadataInfo.from_services(
        "demo", [ServiceInfo(name="test.Other", protocol="tri", port=65536, path="test.Other")]
    )
    infos = {good.revision: good, bad.revision: bad}

    def instance(host, revision):
        return ServiceInstance(
            app="demo",
            host=host,
            port=50051,
            metadata={"dubbo.metadata.revision": revision, "dubbo.metadata.storage-type": "remote"},
        )

    class Instances(Resource):
        @asynccontextmanager
        async def subscribe(self, app):
            snapshots = Latest()
            snapshots.publish([instance("10.0.0.5", good.revision), instance("10.0.0.6", bad.revision)])
            yield aiter(snapshots)

        async def aclose(self):
            pass

    class Report(Resource):
        async def get_app_metadata(self, app, revision):
            return infos[revision]

        async def aclose(self):
            pass

    extensions.register(InstanceRegistry, "memory", lambda url: Instances())
    extensions.register(MetadataReport, "memory", lambda url: Report())

    with anyio.fail_after(5):
        async with ApplicationScope() as scope:
            url = URL.parse("memory://registry").replace(attributes={APPLICATION_SCOPE: scope})
            async with subscribe_by_instance(url, "test.Greeter", ["demo"]) as urls:
                assert await anext(urls) == [URL.parse("tri://10.0.0.5:50051/test.Greeter")]
