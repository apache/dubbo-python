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

"""The Dubbo application: its configuration, and the order it starts and stops in."""

import asyncio
import logging
import signal
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from functools import partial
from os import PathLike
from typing import Self, TypeVar, cast

import anyio

from dubbo.cluster.reference import refer
from dubbo.config import (
    ApplicationConfig,
    ConfigCenterConfig,
    ConsumerConfig,
    DubboConfig,
    MetadataReportConfig,
    ProtocolConfig,
    ProviderConfig,
    ReferenceConfig,
    RegistryConfig,
    ServiceConfig,
    ShutdownConfig,
    TLSConfig,
)
from dubbo.config.data import merge
from dubbo.config.loading import ConfigSource, load_config
from dubbo.config.structure import unstructure_config
from dubbo.config.urls import (
    direct_urls,
    reference_registries,
    reference_url,
    service_urls,
)
from dubbo.constants import CHECK_KEY, DEFAULT_CHECK, DEFAULT_GENERIC, DEFAULT_SHUTWAIT
from dubbo.exceptions import RpcError, Status
from dubbo.extension import ApplicationScope
from dubbo.protocol import get_protocol
from dubbo.protocol.exported import export_services
from dubbo.registry.provider import register_services
from dubbo.rpc.client import GenericService, proxy
from dubbo.rpc.definition import Service, get_definition
from dubbo.rpc.invocation import Invocation, Invoker, Result
from dubbo.url import URL
from dubbo.utils.converters import boolean

__all__ = ["Dubbo"]

T = TypeVar("T")

# Seconds a reference that checks waits at startup for a provider, as for one its own application registers.
_CHECK_GRACE = 3.0
_CHECK_INTERVAL = 0.05
# The signals that stop an application that serves forever.
_SIGNALS = (signal.SIGINT, signal.SIGTERM)

_logger = logging.getLogger(__name__)


class Dubbo(anyio.AsyncContextManagerMixin):
    """A Dubbo application: the services it exports, the references it calls, and their configuration.

    The application runs while ``async with`` holds it: entering starts it,
    and leaving stops it, in the same task::

        app = Dubbo("dubbo.yaml")
        orders = app.refer(OrderService)
        app.export(UserServiceImpl(orders))

        async with app:
            await app.serve_forever()

    Configuration merges from low to high priority: ``sources`` in order,
    each a mapping or a file read by the parser of its suffix (``.yaml``
    needs ``apache-dubbo[yaml]``); the configuration center; environment
    variables named with ``env_prefix``, such as
    ``DUBBO__PROTOCOLS__TRI__PORT=50052``, ``__`` separating keys and JSON
    giving a mapping or a list; then the keyword arguments, and the
    ``config`` of `export` and `refer` and the ``url`` of `refer`. Mappings merge key by key; fields left as ``None`` keep the
    values of lower layers. The configuration center is the one the other
    layers set as ``config_center``, else the first registry that can serve
    as one; it cannot set itself. ``env_prefix=None`` ignores the
    environment. Nothing is read before the application starts.

    Starting prepares each reference to call the providers its ``urls``
    name and those its registries hold, connecting to each in the
    background; enters ``lifespan``; serves each exported service on its
    protocols, ``tri`` on port 50051 when the configuration defines none,
    and registers it; then waits up to 3 seconds in all for the references
    that check to find a provider. A failure closes what has started and
    raises.

    Leaving ``async with`` stops in reverse: the services leave the
    registries, stop and wait for their running calls, which may still
    call the references, and then the references close, all within
    ``shutdown.grace`` seconds, 10 by default, after which what still runs
    is cancelled. Cancelling the task, or a second SIGINT or SIGTERM after
    the one that ended `serve_forever`, stops at once, cancelling the
    running calls. To run beside another framework, enter the application
    where that framework starts and stops in one task, such as an ASGI
    lifespan.

    ``lifespan`` takes the application and returns an async context manager
    holding what the services use, such as a database pool. It is entered
    once the references are ready and before the services serve, and
    exited once they have stopped serving, before the references close.
    While it enters, the references can call other applications, but not
    the services of this one.
    """

    def __init__(
        self,
        *sources: ConfigSource,
        application: ApplicationConfig | None = None,
        registries: Mapping[str, RegistryConfig] | None = None,
        protocols: Mapping[str, ProtocolConfig] | None = None,
        provider: ProviderConfig | None = None,
        consumer: ConsumerConfig | None = None,
        config_center: ConfigCenterConfig | None = None,
        metadata_report: MetadataReportConfig | None = None,
        tls: TLSConfig | None = None,
        shutdown: ShutdownConfig | None = None,
        lifespan: Callable[[Self], AbstractAsyncContextManager[object]] | None = None,
        env_prefix: str | None = "DUBBO__",
    ) -> None:
        for source in sources:
            if not isinstance(source, (str, PathLike, Mapping)):
                raise TypeError(f"configuration source must be a path or a mapping, not {type(source).__name__}")

        self._sources = sources
        self._env_prefix = env_prefix
        sections = {
            "application": application,
            "registries": registries,
            "protocols": protocols,
            "provider": provider,
            "consumer": consumer,
            "config_center": config_center,
            "metadata_report": metadata_report,
            "tls": tls,
            "shutdown": shutdown,
        }
        self._code = cast(dict[str, object], unstructure_config(sections))
        self._lifespan = lifespan
        self._config: DubboConfig | None = None

        # The services, and the contracts of references, by interface.
        self._services: dict[str, Service] = {}
        self._references: dict[str, Service] = {}
        # The generic mode of each reference called generically.
        self._generic: dict[str, str] = {}
        # The url each reference is given in code.
        self._urls: dict[str, str] = {}
        # The settings each reference is given in code by refer, and the services and references the keyword
        # arguments give settings, which export and refer cannot give again.
        self._configs: dict[str, ReferenceConfig] = {}
        self._configured_services = frozenset(provider.services if provider is not None else ())
        self._configured_references = frozenset(consumer.references if consumer is not None else ())
        # From the moment starting begins until stopping ends.
        self._running = False
        # Set while the application runs: what makes the calls of each reference.
        self._invokers: dict[str, Invoker] = {}
        # Set while the application runs: the URLs its services are served with.
        self._exported: tuple[URL, ...] | None = None
        # Whether serve_forever returned on a signal, so that another one while stopping stops at once.
        self._signalled = False

    @property
    def config(self) -> DubboConfig:
        """The merged configuration, available once the application has started.

        Raises:
            RuntimeError: The application has not started.
        """
        if self._config is None:
            raise RuntimeError("the configuration is available once the application has started")
        return self._config

    @property
    def exported_urls(self) -> tuple[URL, ...]:
        """The URLs the services are served with, in the order they were exported, while the application runs.

        Each URL has the port bound, so that a service served on port 0
        tells the port it got. They include the services of the framework,
        such as the MetadataService.

        Raises:
            RuntimeError: The application is not running.
        """
        if self._exported is None:
            raise RuntimeError("the exported URLs are known while the application runs")
        return self._exported

    def export(self, implementation: object, *, config: ServiceConfig | None = None) -> None:
        """Expose ``implementation`` once the application starts.

        ``implementation`` is an object implementing a service contract, or
        a `Service` whose methods all have handlers. The service takes its
        settings from ``config``, or else from the entry of its name in
        ``provider.services``.

        Raises:
            RuntimeError: The application has started.
            TypeError: ``implementation`` does not implement a valid service
                contract, or leaves a method unimplemented.
            ValueError: A service of the same name is already exported, or
                the contract gives two methods the same name, or ``config``
                is given for a service that the ``provider`` argument
                configures.
        """
        self._check_not_started("export")

        service = implementation if isinstance(implementation, Service) else Service.from_implementation(implementation)
        interface = service.interface
        if interface in self._services:
            raise ValueError(f"{interface} is already exported")
        if config is not None:
            if interface in self._configured_services:
                raise ValueError(f"{interface} is already configured in provider.services")
            merge(self._code, {"provider": {"services": {interface: unstructure_config(config)}}})

        self._services[interface] = service

    def refer(self, contract: type[T], *, url: str | None = None, config: ReferenceConfig | None = None) -> T:
        """Return an object of type ``contract`` that calls its service once the application starts.

        The service takes its settings from ``config``, or else from the
        entry of its name in ``consumer.references``. ``url`` names the
        provider to call directly, as in ``tri://127.0.0.1:50051``, over the
        ``urls`` of that entry; it is the short form of ``config.urls``,
        which may name it too, but no other. Referring to it again returns
        another object calling the same service, and may repeat ``url`` and
        ``config``. Calling before the application has started, or after it
        has stopped, raises `RuntimeError`.

        Each method of the object has the name, signature, type annotations
        and docstring of the method of ``contract`` it calls, as `inspect`
        and `typing.get_type_hints` report them, so that it can be given
        where a function is described by them, such as a tool of an agent.

        Raises:
            RuntimeError: The application has started.
            TypeError: ``contract`` is not a valid service contract.
            ValueError: Another contract already refers to the same service,
                or another ``url`` or ``config`` was given for it, or
                ``config`` is given for a service that the ``consumer``
                argument configures, or ``url`` is not what ``config.urls``
                names, or the contract gives two methods the same name.
        """
        self._check_not_started("refer")

        definition = get_definition(contract)
        interface = definition.interface
        if self._references.get(interface, definition) != definition:
            raise ValueError(f"another contract already refers to {interface}")
        self._refer_settings(interface, url, config)
        self._references[interface] = definition

        return proxy(contract, partial(self._invoke, interface))

    def refer_generic(
        self,
        interface: str,
        *,
        url: str | None = None,
        config: ReferenceConfig | None = None,
        generic: str = DEFAULT_GENERIC,
    ) -> GenericService:
        """Return a `GenericService` that calls the service ``interface`` by method name once the application starts.

        The service takes its settings from ``config``, or else from the
        entry of its name in ``consumer.references``, which may configure
        any method; ``url`` names the provider to call directly. Both are
        taken as `refer` takes them. A contract
        may refer to the same service, sharing its settings and providers.
        ``generic`` names the form of the arguments and results, as
        `GenericService` lists them. Calling before the application has
        started, or after it has stopped, raises `RuntimeError`.

        Raises:
            RuntimeError: The application has started.
            ValueError: ``interface`` is empty, ``generic`` names no form,
                another ``url``, ``config`` or ``generic`` was given for it,
                or ``url`` and ``config`` are refused as `refer` refuses them.
        """
        self._check_not_started("refer")

        if not interface:
            raise ValueError("interface must not be empty")
        service = GenericService(interface, partial(self._invoke, interface), generic=generic)
        if self._generic.get(interface, generic) != generic:
            raise ValueError(f"{interface} is already referred to with generic={self._generic[interface]}")
        self._refer_settings(interface, url, config)
        self._generic[interface] = generic

        return service

    async def serve_forever(self) -> None:
        """Serve until the process receives SIGINT or SIGTERM, then return, so that leaving ``async with`` stops the application.

        Another SIGINT or SIGTERM while the application stops makes it stop
        at once, as cancelling does. Where signals cannot be received, such
        as on Windows or outside the main thread, it serves until cancelled.

        Raises:
            RuntimeError: The application has not started.
        """
        if self._config is None or not self._running:
            raise RuntimeError("the application serves once it has started")

        try:
            with anyio.open_signal_receiver(*_SIGNALS) as signals:
                async for received in signals:
                    _logger.info("Stopping on %s", signal.Signals(received).name)
                    self._signalled = True
                    return
        except (NotImplementedError, RuntimeError, ValueError):
            # The services serve in their own tasks; this one only waits to be cancelled.
            await anyio.sleep_forever()

    @asynccontextmanager
    async def __asynccontextmanager__(self) -> AsyncGenerator[Self]:
        """Start the application, reading and validating its configuration, and stop it on leaving.

        A failure closes what has been opened so far. Stopping, and the
        closing after a failure, takes at most ``shutdown.grace`` in all;
        what still runs then is cancelled. Cancelling the task stops at
        once, without the waits.

        Raises:
            RuntimeError: The application has already started.
            dubbo.config.ConfigError: The configuration cannot be read or is
                invalid, configures a method that its service does not have,
                or gives a reference neither ``urls`` nor a registry.
            dubbo.extension.ExtensionError: The configuration names an
                extension that is not installed, or one cannot be loaded.
            ValueError: A URL parameter is invalid.
            OSError: An address cannot be bound.
            dubbo.RpcError: ``UNAVAILABLE``: a reference that checks has no
                provider.
            dubbo.transport.zookeeper.ZookeeperError: A ZooKeeper registry
                cannot be reached.
            dubbo.transport.nacos.NacosError: A Nacos registry cannot be
                reached.
        """
        if self._running:
            raise RuntimeError("the application has already started")
        self._running = True

        started = False
        ended: BaseException | None = None
        forced = False

        def stop_at_once(received: signal.Signals) -> None:
            nonlocal forced
            if not forced:
                _logger.info("Stopping at once on a second %s", received.name)
                forced = True
                stopping.cancel()

        # AnyIO receives signals only in a task, while a handler of the loop cancels the scope without one.
        loop = asyncio.get_running_loop()
        try:
            # Entered before what the application opens, so that its deadline bounds the closing of all of it.
            with anyio.CancelScope() as stopping:
                async with AsyncExitStack() as stack:
                    try:
                        await self._start(stack)
                        started = True
                        yield self
                    except BaseException as error:
                        ended = error
                        raise
                    finally:
                        if isinstance(ended, anyio.get_cancelled_exc_class()):
                            # A cancellation of the task, as asyncio's, may reach it once; the closing must see it too.
                            forced = True
                            stopping.cancel()
                        else:
                            stopping.deadline = anyio.current_time() + self._shutdown_budget()
                        if self._signalled:
                            for received in _SIGNALS:
                                loop.add_signal_handler(received, stop_at_once, received)
            if stopping.cancelled_caught and not forced:
                _logger.warning(
                    "Stopping took longer than %.1f seconds; what still ran was cancelled", self._shutdown_budget()
                )
            # The scope swallows the cancellation of its deadline, and with it what ended the application.
            if stopping.cancelled_caught and ended is not None:
                raise ended
        finally:
            if self._signalled:
                for received in _SIGNALS:
                    loop.remove_signal_handler(received)
                self._signalled = False
            if not started:
                self._config = None
            self._running = False

    async def _invoke(self, interface: str, invocation: Invocation) -> Result:
        try:
            invoker = self._invokers[interface]
        except KeyError:
            raise RuntimeError(f"{interface} is called only while the application runs") from None

        return await invoker.invoke(invocation)

    async def _start(self, stack: AsyncExitStack) -> None:
        """Open into ``stack`` what the application runs with, in the order that it closes in reverse."""
        # What the extensions of the application share, such as its protocols and the connections to its
        # registries: each opens on first use, and all close after everything else.
        scope = await stack.enter_async_context(ApplicationScope())
        config = await load_config(self._sources, env_prefix=self._env_prefix, code=self._code, scope=scope)
        # From now on, so that the closing after a failure takes the shutdown budget it configures.
        self._config = config
        services = {interface: service_urls(config, service, scope) for interface, service in self._services.items()}
        # A reference called only generically has no methods it knows.
        definitions = {interface: Service(interface=interface, methods=()) for interface in self._generic}
        definitions |= self._references
        references = {
            interface: reference_url(config, definition, scope, generic=interface in self._generic)
            for interface, definition in definitions.items()
        }
        # A reference calls the providers its urls name directly and those its registries hold.
        direct = {interface: direct_urls(config, url) for interface, url in references.items()}
        registries = {interface: reference_registries(config, interface, scope) for interface in references}

        # References first, to close last, so that services can call them while they stop. Calls are refused
        # before each closes.
        for interface, url in references.items():
            invoker = await stack.enter_async_context(
                refer(
                    url,
                    definitions[interface],
                    direct[interface],
                    registries[interface],
                    generic=None if interface in self._references else self._generic[interface],
                )
            )
            self._invokers[interface] = invoker
            stack.callback(self._invokers.pop, interface)

        # Before serving and after stopping to serve, so that the calls of the services find what it opens.
        if self._lifespan is not None:
            await stack.enter_async_context(self._lifespan(self))

        exported = await stack.enter_async_context(export_services(config, services, self._services, scope))
        metadata_urls = await stack.enter_async_context(register_services(config, exported, scope))
        self._exported = (*(service.url for service in exported), *metadata_urls)
        stack.callback(setattr, self, "_exported", None)
        # Stopping tells the callers first, while the services leave the registries and keep serving.
        for name in {url.protocol for urls in services.values() for url in urls}:
            stack.callback((await get_protocol(name, scope)).announce_shutdown)
        # After registering, so that a reference to a service of this application finds it.
        await _check_references(references, self._invokers)

    def _refer_settings(self, interface: str, url: str | None, config: ReferenceConfig | None) -> None:
        """Have the reference ``interface`` take ``config`` and call ``url`` directly, each given for it in code once."""
        if url is not None and self._urls.get(interface, url) != url:
            raise ValueError(f"{interface} is already referred to at another url")
        if config is not None:
            if interface in self._configured_references:
                raise ValueError(f"{interface} is already configured in consumer.references")
            if self._configs.get(interface, config) != config:
                raise ValueError(f"{interface} is already referred to with other settings")
        given_url = self._urls.get(interface) if url is None else url
        given = self._configs.get(interface) if config is None else config
        if given_url is not None and given is not None and given.urls and given.urls != (given_url,):
            raise ValueError(f"the url and the config of {interface} name different providers")

        if config is not None and interface not in self._configs:
            self._configs[interface] = config
            merge(self._code, {"consumer": {"references": {interface: unstructure_config(config)}}})
        if url is not None and interface not in self._urls:
            self._urls[interface] = url
            merge(self._code, {"consumer": {"references": {interface: {"urls": [url]}}}})

    def _check_not_started(self, action: str) -> None:
        if self._running:
            raise RuntimeError(f"cannot {action} once the application has started")

    def _shutdown_budget(self) -> float:
        grace = None if self._config is None else self._config.shutdown.grace
        return DEFAULT_SHUTWAIT if grace is None else grace


async def _check_references(references: Mapping[str, URL], invokers: Mapping[str, Invoker]) -> None:
    """Wait a moment for each reference that sets ``check`` to have a provider connected.

    Raises:
        RpcError: ``UNAVAILABLE``: some have none.
    """
    pending = [name for name, url in references.items() if url.get_parameter(CHECK_KEY, boolean, DEFAULT_CHECK)]
    with anyio.move_on_after(_CHECK_GRACE):
        while pending := [name for name in pending if not invokers[name].available]:
            await anyio.sleep(_CHECK_INTERVAL)

    if pending:
        raise RpcError(
            Status.UNAVAILABLE,
            f"no provider of {', '.join(sorted(pending))} is available; set check to false to start without one",
        )
