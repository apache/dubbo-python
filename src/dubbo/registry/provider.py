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

"""How the services of an application are served and registered: by interface, and through the application instance."""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import cast

import anyio
import attrs
from anyio.abc import TaskGroup, TaskStatus

from dubbo.cluster.configurator import Overrides
from dubbo.config import DubboConfig, MetadataType, RegistryMode
from dubbo.config.urls import internal_service_urls
from dubbo.constants import (
    APPLICATION_KEY,
    CLUSTER_KEY,
    DEFAULT_METADATA_TYPE,
    DEFAULT_UNREGISTER_WAIT,
    DEPRECATED_KEY,
    DUBBO_VERSION,
    DUBBO_VERSION_KEY,
    EXTRA_KEYS_KEY,
    GROUP_KEY,
    INTERFACE_KEY,
    LOADBALANCE_KEY,
    METHODS_KEY,
    PATH_KEY,
    PREFER_SERIALIZATION_KEY,
    RELEASE_KEY,
    SERIALIZATION_KEY,
    SIDE_KEY,
    TIMEOUT_KEY,
    TIMESTAMP_KEY,
    TOKEN_KEY,
    VERSION_KEY,
    WARMUP_KEY,
    WEIGHT_KEY,
)
from dubbo.extension import ApplicationScope
from dubbo.metadata import MetadataInfo, MetadataReport, ServiceInfo, get_metadata_report
from dubbo.metadata.instance import instance_metadata
from dubbo.metadata.service.server import LocalMetadata
from dubbo.protocol.exported import ExportedService
from dubbo.url import ADVERTISED_PORT, URL
from dubbo.utils import Latest, backoff, create_background_task_group
from dubbo.utils.converters import comma_separated

from .base import (
    InstanceRegistry,
    InterfaceRegistry,
    ServiceInstance,
    get_instance_registry,
    get_interface_registry,
    registry_mode,
)
from .registration import (
    RELEASE,
    published_parameters,
    registered_host,
    registered_parameters,
    registers,
    registration_time,
    simplified,
)

__all__ = ["register_services"]

_logger = logging.getLogger(__name__)

# Parameters that simplified provider URLs keep, besides those of their methods and the extra keys.
_PROVIDER_KEYS = frozenset({
    APPLICATION_KEY, "codec", "exchanger", SERIALIZATION_KEY, PREFER_SERIALIZATION_KEY, CLUSTER_KEY, "connections",
    DEPRECATED_KEY, GROUP_KEY, LOADBALANCE_KEY, "mock", PATH_KEY, TIMEOUT_KEY, TOKEN_KEY, VERSION_KEY, WARMUP_KEY,
    WEIGHT_KEY, DUBBO_VERSION_KEY, RELEASE_KEY, SIDE_KEY, "ipv6", "serialize.packable.factory", "auth",
    "authenticator", "username", "password",
})  # fmt: skip


@asynccontextmanager
async def register_services(
    config: DubboConfig, services: Sequence[ExportedService], scope: ApplicationScope
) -> AsyncGenerator[tuple[URL, ...]]:
    """Register ``services`` of the application of ``scope`` with their registries until the context exits.

    It holds the URLs the MetadataService is served with, if the registering serves it.

    Registries that set ``register`` to false get nothing. In those that
    register by interface, the URL of each service is registered, with the
    parameters consumers take. In those that register instances, the
    application registers one instance whose metadata lists those URLs, and
    records that it provides each interface; with ``local`` metadata, the
    first such instance starts serving the MetadataService on the server of
    the services, as `dubbo.metadata.service.server.LocalMetadata` does.
    The URLs carry ``application.advertised_host`` and the advertised port
    of their protocol, else of the application, when set. A registry URL also gets the parameters of the services that
    its ``extra-keys`` name; with ``simplified=true``, it gets only those
    and the parameters consumers need.

    With a configuration center, the override rules of the providers change
    the registered URLs, and each change registers them again; a failure to
    register them is logged and tried again. Each change, and the rules at
    the start, also reach how the services serve, through ``reconfigure``.
    When the context exits without an error, it waits
    ``shutdown.unregister_wait`` after unregistering, if it registered
    anything.

    Raises:
        ConfigError: Metadata is ``local`` but no service is served over tri or dubbo.
        ValueError: A parameter of a registry is invalid.
        ZookeeperError: A ZooKeeper registry cannot be reached.
    """
    application = config.application
    async with AsyncExitStack() as stack:
        changes: Latest[None] = Latest()
        published: list[_Published] = []
        for service in services:
            registries = [registry for registry in service.registries if registers(registry)]
            if not registries:
                continue
            url = _provider_url(service).replace(
                host=await registered_host(application.advertised_host or service.url.host, registries),
                port=_advertised_port(service.url),
            )
            overrides = await stack.enter_async_context(Overrides(url, "provider", lambda: changes.publish(None)))
            published.append(_Published(service=service, url=url, registries=registries, overrides=overrides))

        def reconfigure() -> None:
            for each in published:
                each.reconfigure()

        metadata = LocalMetadata(
            internal_service_urls(config, [service.interface for service in services], scope), stack
        )
        keepers = await stack.enter_async_context(create_background_task_group())
        # Cancelled after the callbacks below have released every registration.
        stack.callback(keepers.cancel_scope.cancel)
        kept = _Kept(keepers)
        metadata_type = MetadataType(application.metadata_type or DEFAULT_METADATA_TYPE)
        registrations: list[_InterfaceRegistration | _InstanceRegistration] = []
        for registry in dict.fromkeys(registry for each in published for registry in each.registries):
            mode = registry_mode(registry)
            if mode is not RegistryMode.INSTANCE:
                registrations.append(
                    _InterfaceRegistration(registry=registry, client=await get_interface_registry(registry), kept=kept)
                )
            if mode is not RegistryMode.INTERFACE:
                registrations.append(
                    _InstanceRegistration(
                        registry=registry,
                        client=await get_instance_registry(registry),
                        report=await get_metadata_report(registry),
                        metadata_type=metadata_type,
                        metadata=metadata,
                        kept=kept,
                    )
                )

        async def register() -> None:
            for registration in registrations:
                registry = registration.registry
                await registration.register(
                    [each.registered_url(registry) for each in published if registry in each.registries]
                )
            # Only the revisions of registered instances stay served.
            metadata.retain(
                {
                    registration.revision
                    for registration in registrations
                    if isinstance(registration, _InstanceRegistration) and registration.revision is not None
                }
            )

        for registration in registrations:
            stack.push_async_callback(registration.unregister)
        reconfigure()
        await register()

        task_group = await stack.enter_async_context(create_background_task_group())
        stack.callback(task_group.cancel_scope.cancel)
        task_group.start_soon(_register_on_change, changes, reconfigure, register)

        yield metadata.urls

    # Consumers stop calling once they notice, while the services still serve.
    if published:
        wait = config.shutdown.unregister_wait
        await anyio.sleep(DEFAULT_UNREGISTER_WAIT if wait is None else wait)


@attrs.define(frozen=True, kw_only=True)
class _Published:
    """The URL a service registers before the override rules, the registries it registers with, and its rules."""

    service: ExportedService
    url: URL
    registries: list[URL]
    overrides: Overrides

    def registered_url(self, registry: URL) -> URL:
        """Return the URL to register with ``registry``, with its extra keys, after the override rules."""
        url = _with_extra_keys(self.url, self.service.url, registry)
        return _registered_provider_url(self.overrides.configure([url])[0], registry)

    def reconfigure(self) -> None:
        """Apply to how the service serves the parameters that the override rules change."""
        configured = self.overrides.configure([self.url])[0].parameters
        self.service.reconfigure(
            {key: value for key, value in configured.items() if self.url.parameters.get(key) != value}
        )


async def _register_on_change(
    changes: Latest[None], reconfigure: Callable[[], None], register: Callable[[], Awaitable[None]]
) -> None:
    """Call ``reconfigure``, then ``register`` until it succeeds, after each change of the override rules.

    A change applies at once even while ``register`` still fails for an
    earlier one, whose attempts it replaces.
    """
    registering = anyio.CancelScope()
    async with anyio.create_task_group() as task_group:
        async for _ in changes:
            reconfigure()
            registering.cancel()
            registering = anyio.CancelScope()
            task_group.start_soon(_register_until_done, register, registering)


async def _register_until_done(register: Callable[[], Awaitable[None]], scope: anyio.CancelScope) -> None:
    with scope:
        for delay in backoff():
            try:
                await register()
                return
            except Exception:
                _logger.warning(
                    "Cannot register the services as their override rules changed; trying again in %.1f seconds",
                    delay,
                    exc_info=True,
                )
                await anyio.sleep(delay)


def _provider_url(service: ExportedService) -> URL:
    """Return the URL that registries publish for ``service``: what its consumers take from it."""
    methods = [method.name for method in service.definition.methods]
    parameters = published_parameters(service.url.parameters, methods) | registered_parameters(methods)

    return service.url.replace(
        path=service.interface,
        parameters=parameters | {SIDE_KEY: "provider", INTERFACE_KEY: service.interface},
    )


def _with_extra_keys(url: URL, served: URL, registry: URL) -> URL:
    """Return ``url`` with the parameters of ``served`` that the ``extra-keys`` of ``registry`` name."""
    extra = comma_separated(registry.parameters.get(EXTRA_KEYS_KEY, ""))
    return url.update_parameters({key: served.parameters[key] for key in extra if key in served.parameters})


def _registered_provider_url(url: URL, registry: URL) -> URL:
    """Return ``url`` as ``registry`` takes it: whole, or simplified to what consumers need."""
    if not simplified(registry):
        return url

    parameters = url.parameters
    kept = _PROVIDER_KEYS | set(comma_separated(registry.parameters.get(EXTRA_KEYS_KEY, "")))
    # The interface is kept where the path differs, so that consumers still find the service by it.
    if url.path != parameters.get(INTERFACE_KEY, url.path):
        kept |= {INTERFACE_KEY}
    prefixes = tuple(f"{method}." for method in comma_separated(parameters.get(METHODS_KEY, "")))

    return url.replace(
        parameters={
            key: value for key, value in parameters.items() if value and (key in kept or key.startswith(prefixes))
        },
    )


@attrs.define(kw_only=True, eq=False)
class _InterfaceRegistration:
    """The URLs of the services registered with a registry that registers by interface."""

    registry: URL
    client: InterfaceRegistry
    kept: "_Kept"
    # What releases each URL registered, in the order they were.
    registered: dict[URL, Callable[[], Awaitable[None]]] = attrs.field(factory=dict)

    async def register(self, urls: list[URL]) -> None:
        """Register ``urls`` in place of those registered: the new ones first, so that no service is ever missing."""
        for url in urls:
            if url not in self.registered:
                self.registered[url] = await self.kept.keep(self.client.register(url))
        for url in [url for url in self.registered if url not in urls]:
            await self.registered.pop(url)()

    async def unregister(self) -> None:
        while self.registered:
            await self.registered.pop(next(iter(self.registered)))()


@attrs.define(kw_only=True, eq=False)
class _InstanceRegistration:
    """The instance of the application registered with a registry that registers instances."""

    registry: URL
    client: InstanceRegistry
    kept: "_Kept"
    report: MetadataReport
    metadata_type: MetadataType
    metadata: LocalMetadata
    # What releases the instance registered.
    release: Callable[[], Awaitable[None]] | None = None
    # The registration time of the first instance, which every later one keeps.
    timestamp: str = attrs.field(factory=registration_time)
    revision: str | None = None

    async def register(self, urls: list[URL]) -> None:
        """Register the instance that serves ``urls``, replacing the one registered when its metadata changes."""
        # Registries hold URLs of this application only, which DubboConfig gives a name.
        app = urls[0].parameters[APPLICATION_KEY]
        info = MetadataInfo.from_services(app, [_service_info(url) for url in urls])
        if info.revision == self.revision:
            return

        metadata_service = metadata_version = None
        if self.metadata_type is MetadataType.LOCAL:
            metadata_service = _metadata_service_parameters(await self.metadata.serve(info))
            metadata_version = self.metadata.version
        else:
            await self.report.publish_app_metadata(info)
        values = instance_metadata(info, self.metadata_type, urls, metadata_service, metadata_version) | {
            TIMESTAMP_KEY: self.timestamp
        }

        first = urls[0]
        assert first.host is not None
        assert first.port is not None
        if self.release is None:
            for interface in sorted({url.path for url in urls}):
                await self.report.register_service_app_mapping(interface, app)
        instance = ServiceInstance(app=app, host=first.host, port=first.port, metadata=values)
        # The new instance replaces the one before, which then leaves it on exiting.
        release, replaced = await self.kept.keep(self.client.register(instance)), self.release
        self.release, self.revision = release, info.revision
        if replaced is not None:
            await replaced()

    async def unregister(self) -> None:
        release, self.release = self.release, None
        if release is not None:
            await release()


def _advertised_port(url: URL) -> int:
    """Return the port to register for the server of ``url``: the one the configuration sets, else the one bound."""
    port = cast(int | None, url.attributes.get(ADVERTISED_PORT)) or url.port
    assert port is not None
    return port


def _metadata_service_parameters(url: URL) -> dict[str, str]:
    """Return the URL parameters that the instance metadata publishes for the MetadataService served with ``url``."""
    return {
        VERSION_KEY: url.parameters[VERSION_KEY],
        DUBBO_VERSION_KEY: DUBBO_VERSION,
        RELEASE_KEY: RELEASE,
        SIDE_KEY: "provider",
        "port": str(_advertised_port(url)),
        "protocol": url.protocol,
    }


def _service_info(url: URL) -> ServiceInfo:
    assert url.port is not None
    return ServiceInfo(
        name=url.parameters.get(INTERFACE_KEY, url.path),
        group=url.parameters.get(GROUP_KEY),
        version=url.parameters.get(VERSION_KEY),
        protocol=url.protocol,
        port=url.port,
        path=url.path,
        # The registration time would give every start a new revision.
        params={key: value for key, value in url.parameters.items() if key != TIMESTAMP_KEY},
    )


class _Kept:
    """Registrations kept each in a task of ``task_group``, which enters and exits it, until released."""

    def __init__(self, task_group: TaskGroup) -> None:
        self._task_group = task_group

    async def keep(self, registration: AbstractAsyncContextManager[None]) -> Callable[[], Awaitable[None]]:
        """Enter ``registration`` in a task of its own, raising what entering raises, and return what exits it.

        The function returned exits the registration, raising what exiting
        raises, and returns once it has exited.
        """
        keeper = _Keeper(registration=registration)
        await self._task_group.start(keeper.keep)
        return keeper.release


@attrs.define(kw_only=True, eq=False)
class _Keeper:
    """A registration that a task enters and exits: what tells the task to exit it, and how exiting went."""

    registration: AbstractAsyncContextManager[None]
    released: anyio.Event = attrs.field(factory=anyio.Event)
    exited: anyio.Event = attrs.field(factory=anyio.Event)
    error: Exception | None = None

    async def keep(self, *, task_status: TaskStatus[None]) -> None:
        """Enter the registration, and exit it once released."""
        try:
            async with self.registration:
                task_status.started()
                await self.released.wait()
        except Exception as error:
            # Before it is entered, start raises what entering does.
            if not self.released.is_set():
                raise
            self.error = error
        finally:
            self.exited.set()

    async def release(self) -> None:
        """Exit the registration, raising what exiting raises, and return once it has exited."""
        self.released.set()
        await self.exited.wait()
        if self.error is not None:
            raise self.error
