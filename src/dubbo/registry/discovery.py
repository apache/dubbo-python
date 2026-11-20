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

"""How a reference finds the provider URLs a registry holds: registered by interface, or through instances."""

import logging
import math
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Collection, Hashable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Generic, Self, TypeVar, cast

import anyio
import attrs
from anyio.abc import TaskGroup, TaskStatus

from dubbo.exceptions import DubboError
from dubbo.extension import Resource
from dubbo.metadata import MetadataInfo, MetadataReport, get_metadata_report
from dubbo.metadata.instance import InstanceMetadata, read_metadata
from dubbo.url import APPLICATION_SCOPE, METADATA_CONSUMER_URL, URL
from dubbo.utils import Latest, backoff, create_background_task_group, follow

from .base import InstanceRegistry, ServiceInstance, get_instance_registry, get_interface_registry

__all__ = ["subscribe_by_instance", "subscribe_by_interface"]

_logger = logging.getLogger(__name__)

K = TypeVar("K", bound=Hashable)
T = TypeVar("T")

# The URLs of the services of an application, by service path.
_Services = Mapping[str, list[URL]]


@asynccontextmanager
async def subscribe_by_interface(
    registry: URL, interface: str, *, group: str | None, version: str | None
) -> AsyncGenerator[AsyncIterator[list[URL]]]:
    """Watch the provider URLs of ``interface`` registered by interface in ``registry`` until the context exits.

    The arguments and the iterator follow the contract of ``InterfaceRegistry.subscribe``.
    """
    implementation = await get_interface_registry(registry)
    async with implementation.subscribe(interface, group=group, version=version) as snapshots:
        yield snapshots


@asynccontextmanager
async def subscribe_by_instance(
    registry: URL, interface: str, apps: Collection[str] | None
) -> AsyncGenerator[AsyncIterator[list[URL]]]:
    """Watch the provider URLs of ``interface`` until the context exits, from the instances ``registry`` holds.

    The instances are those of ``apps``, else of the applications mapped to
    ``interface``. The references of the application of ``registry`` share
    one watch of each mapping and each application.
    """
    instances = await get_instance_registry(registry)
    report = await get_metadata_report(registry)
    consumer = cast(URL | None, registry.attributes.get(METADATA_CONSUMER_URL)) or URL(
        protocol="consumer", attributes={APPLICATION_SCOPE: registry.scope}
    )
    resolver = await registry.scope.share(
        (_InstanceResolver, registry), lambda: _InstanceResolver(instances, report, consumer)
    )
    async with resolver.subscribe(interface, apps) as snapshots:
        yield snapshots


class _InstanceResolver(Resource):
    """Finds the providers of interfaces in one registry through the instances of the applications that provide them.

    The metadata report maps an interface to the applications that provide
    it. Each instance of an application registers the revision of its
    metadata, which lists the services of the application, and that
    metadata with the address of the instance gives the URLs of its
    services. The subscriptions share one watch of each mapping and each
    application, which runs while some subscription follows it, so an
    application is watched, and the metadata of each revision read, once
    however many of its services are referenced.
    """

    def __init__(self, registry: InstanceRegistry, report: MetadataReport, consumer: URL) -> None:
        """The MetadataService of instances is called with the parameters and the attributes of ``consumer``."""
        self._registry = registry
        self._report = report
        self._consumer = consumer
        self._stack = AsyncExitStack()
        self._mappings: _SharedWatches[str, frozenset[str]] | None = None
        self._apps: _SharedWatches[str, _Services] | None = None

    @asynccontextmanager
    async def subscribe(self, interface: str, apps: Collection[str] | None) -> AsyncGenerator[AsyncIterator[list[URL]]]:
        """Watch the provider URLs of ``interface`` until the context exits, in ``apps``, else in those mapped to it.

        The iterator yields the current URLs first, then the URLs after each
        change. The first URLs come once the mapping is read, which may fail,
        and every application has been watched once. An application whose
        watch fails has no URLs and is watched again after a delay. After the
        first URLs, the iterator neither raises nor ends until the context
        exits.
        """
        if self._mappings is None or self._apps is None:
            raise RuntimeError("the resolver is closed")

        async with create_background_task_group() as task_group:
            watch = _InterfaceWatch(interface, self._apps, task_group)
            if apps is not None:
                await watch.follow_apps(apps)
            else:
                await task_group.start(watch.follow_mapping, self._mappings)
            try:
                yield aiter(watch.latest)
            finally:
                task_group.cancel_scope.cancel()

    async def aclose(self) -> None:
        self._mappings = self._apps = None
        await self._stack.aclose()

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as stack:
            task_group = await stack.enter_async_context(anyio.create_task_group())
            stack.callback(task_group.cancel_scope.cancel)
            self._mappings = _SharedWatches(task_group, self._watch_mapping)
            self._apps = _SharedWatches(task_group, self._watch_app)
            self._stack = stack.pop_all()

        return self

    async def _watch_mapping(self, interface: str, latest: Latest[frozenset[str]]) -> None:
        async with self._report.subscribe_service_app_mapping(interface) as mappings:
            async for apps in mappings:
                latest.publish(apps)

    async def _watch_app(self, app: str, latest: Latest[_Services]) -> None:
        metadata = _AppMetadata(app=app, report=self._report, consumer=self._consumer)
        changes: Latest[list[ServiceInstance]] = Latest()

        async def receive() -> None:
            async for instances in snapshots:
                changes.publish(instances)
            changes.close(RuntimeError(f"the watch of the instances of {app} ended"))

        async with self._registry.subscribe(app) as snapshots, anyio.create_task_group() as task_group:
            task_group.start_soon(receive)
            reader = aiter(changes)
            instances = await anext(reader)
            delays = backoff()
            while True:
                services, complete = await metadata.resolve(instances)
                latest.publish(services)

                # Metadata that could not be read is read again later.
                if complete:
                    delays = backoff()
                with anyio.move_on_after(math.inf if complete else next(delays)):
                    instances = await anext(reader)


class _InterfaceWatch:
    """The provider URLs of one interface across the applications that provide it."""

    def __init__(self, interface: str, apps: "_SharedWatches[str, _Services]", task_group: TaskGroup) -> None:
        self.latest: Latest[list[URL]] = Latest()
        self._interface = interface
        self._apps = apps
        self._task_group = task_group
        self._urls: dict[str, list[URL]] = {}
        self._scopes: dict[str, anyio.CancelScope] = {}
        self._started = False

    async def follow_mapping(
        self, mappings: "_SharedWatches[str, frozenset[str]]", *, task_status: TaskStatus[None]
    ) -> None:
        """Follow the applications the mapping names; the first names fail the subscription if they cannot be read."""
        await follow(
            lambda: mappings.follow(self._interface),
            self.follow_apps,
            f"the applications that provide {self._interface}",
            task_status=task_status,
        )

    async def follow_apps(self, apps: Collection[str]) -> None:
        """Follow ``apps`` from now on, returning once each new one has been watched once."""
        for app in self._scopes.keys() - set(apps):
            self._scopes.pop(app).cancel()
            self._urls.pop(app, None)

        added = sorted(set(apps) - self._scopes.keys())
        for app in added:
            self._scopes[app] = anyio.CancelScope()
        async with anyio.create_task_group() as starting:
            for app in added:
                starting.start_soon(self._task_group.start, self._follow_app, app, self._scopes[app])

        self._started = True
        self._publish()

    async def _follow_app(self, app: str, scope: anyio.CancelScope, *, task_status: TaskStatus[None]) -> None:
        async def receive(services: _Services) -> None:
            # A follower replaced after its application left and came back publishes nothing.
            if self._scopes.get(app) is scope:
                self._urls[app] = services.get(self._interface, [])
                self._publish()

        with scope:
            await follow(
                lambda: self._apps.follow(app),
                receive,
                f"the instances of {app}",
                retry_first=True,
                task_status=task_status,
            )

    def _publish(self) -> None:
        if self._started:
            self.latest.publish([url for app in sorted(self._urls) for url in self._urls[app]])


@attrs.define(kw_only=True, eq=False)
class _Watch(Generic[T]):
    latest: Latest[T] = attrs.field(factory=Latest)
    scope: anyio.CancelScope = attrs.field(factory=anyio.CancelScope)
    followers: int = 0


class _SharedWatches(Generic[K, T]):
    """Runs one watch per key while it has followers, who share the values it publishes.

    A watch that fails before its first value fails the followers waiting
    for it. One that fails or ends after it breaks the contract of what it
    watches: that is logged, and the iterations of its followers end. Either
    way it is forgotten, so the next follower starts it again.
    """

    def __init__(self, task_group: TaskGroup, watch: Callable[[K, Latest[T]], Awaitable[None]]) -> None:
        self._task_group = task_group
        self._watch = watch
        self._watches: dict[K, _Watch[T]] = {}

    @asynccontextmanager
    async def follow(self, key: K) -> AsyncGenerator[AsyncIterator[T]]:
        """Follow the watch of ``key``, iterating its latest value first."""
        watch = self._watches.get(key)
        if watch is None:
            watch = self._watches[key] = _Watch()
            self._task_group.start_soon(self._run, key, watch)

        watch.followers += 1
        try:
            yield aiter(watch.latest)
        finally:
            watch.followers -= 1
            if not watch.followers:
                watch.scope.cancel()
                self._forget(key, watch)

    async def _run(self, key: K, watch: _Watch[T]) -> None:
        with watch.scope:
            try:
                await self._watch(key, watch.latest)
                error: Exception = RuntimeError(f"the watch of {key!r} ended")
            except Exception as failure:
                error = failure

            self._forget(key, watch)
            if watch.latest.empty:
                watch.latest.close(error)
                return

            _logger.error("The watch of %r stopped after its first value", key, exc_info=error)
            watch.latest.close()

    def _forget(self, key: K, watch: _Watch[T]) -> None:
        # A watch that has been replaced leaves its replacement alone.
        if self._watches.get(key) is watch:
            del self._watches[key]


@attrs.define(frozen=True, kw_only=True, eq=False)
class _Resolved:
    """The URLs found for an instance, and the instance metadata and the MetadataInfo they were made from."""

    metadata: InstanceMetadata
    info: MetadataInfo
    urls: list[URL]


@attrs.define(kw_only=True, eq=False)
class _AppMetadata:
    """Turns the instances of one application into the URLs of its services, reading its metadata once per revision."""

    app: str
    report: MetadataReport
    # What the MetadataService of its instances is called with.
    consumer: URL
    # The metadata of the revisions in use.
    infos: dict[str, MetadataInfo] = attrs.field(factory=dict)
    # What was last found for each instance, by id.
    resolved: dict[str, _Resolved] = attrs.field(factory=dict)

    async def resolve(self, instances: list[ServiceInstance]) -> tuple[_Services, bool]:
        """Return the URLs of the services, and whether the metadata of every revision could be read.

        An instance whose revision cannot be read yet keeps the URLs it had,
        and one whose metadata and revision do not change keeps the same URLs.
        """
        found: dict[str, InstanceMetadata] = {}
        for instance in instances:
            try:
                metadata = InstanceMetadata.from_metadata(instance.host, instance.port, instance.metadata)
            except ValueError:
                _logger.warning("Ignoring an instance of %s", self.app, exc_info=True)
                continue
            if metadata is not None:
                found[instance.id] = metadata

        by_revision: dict[str, list[InstanceMetadata]] = {}
        for metadata in found.values():
            by_revision.setdefault(metadata.revision, []).append(metadata)
        self.infos = {revision: info for revision, info in self.infos.items() if revision in by_revision}
        async with anyio.create_task_group() as task_group:
            for revision, members in by_revision.items():
                if revision not in self.infos:
                    task_group.start_soon(self._read, revision, members)

        resolved: dict[str, _Resolved] = {}
        for instance_id, metadata in found.items():
            info = self.infos.get(metadata.revision)
            kept = self.resolved.get(instance_id)
            if info is None:
                if kept is not None:
                    resolved[instance_id] = kept
            elif kept is not None and kept.metadata == metadata and kept.info is info:
                resolved[instance_id] = kept
            else:
                resolved[instance_id] = _Resolved(metadata=metadata, info=info, urls=self._service_urls(metadata, info))
        self.resolved = resolved

        services: dict[str, list[URL]] = {}
        for each in resolved.values():
            for url in each.urls:
                services.setdefault(url.path, []).append(url)

        return services, by_revision.keys() <= self.infos.keys()

    async def _read(self, revision: str, instances: list[InstanceMetadata]) -> None:
        for instance in instances:
            try:
                info = await read_metadata(self.app, instance, self.report, self.consumer)
            except (DubboError, OSError, ValueError):
                _logger.warning(
                    "Cannot read the metadata of %s:%d at revision %s; trying another instance",
                    instance.host,
                    instance.port,
                    revision,
                    exc_info=True,
                )
                continue

            if info is not None and info.services:
                self.infos[revision] = info
                return

    def _service_urls(self, metadata: InstanceMetadata, info: MetadataInfo) -> list[URL]:
        try:
            return metadata.service_urls(info)
        except ValueError:
            # Kept as no URLs, so that the other instances still have theirs and this one is logged once.
            _logger.warning(
                "Ignoring the instance %s:%d of %s, whose metadata at revision %s holds no valid URL",
                metadata.host,
                metadata.port,
                self.app,
                metadata.revision,
                exc_info=True,
            )
            return []
