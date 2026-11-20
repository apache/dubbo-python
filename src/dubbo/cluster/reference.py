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

"""How a reference calls its providers: those it names, and those its registries hold."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from functools import partial

from dubbo.cluster import DynamicDirectory, StaticDirectory, create_cluster, create_routers
from dubbo.config import RegistryMode
from dubbo.constants import (
    CLUSTER_KEY,
    DEFAULT_ROUTERS,
    GROUP_KEY,
    PREFERRED_KEY,
    PROVIDED_BY_KEY,
    REFERENCE_FILTER_KEY,
    REGISTRY_PREFERRED_KEY,
    REGISTRY_ZONE_KEY,
    ROUTER_KEY,
    VERSION_KEY,
    WEIGHT_KEY,
    ZONE_AWARE_CLUSTER,
    ZONE_KEY,
)
from dubbo.extension import ApplicationScope
from dubbo.filter import chain_filters, get_attempt_filters, get_filters
from dubbo.protocol import get_protocol
from dubbo.registry import registry_mode
from dubbo.registry.consumer import Consumer, register_consumer
from dubbo.registry.discovery import subscribe_by_instance, subscribe_by_interface
from dubbo.registry.registration import registered_host
from dubbo.rpc.definition import Service
from dubbo.rpc.invocation import Invoker
from dubbo.url import URL
from dubbo.utils.converters import boolean, comma_separated

__all__ = ["refer"]


@asynccontextmanager
async def refer(
    url: URL, definition: Service, providers: Sequence[URL], registries: Sequence[URL], *, generic: str | None
) -> AsyncGenerator[Invoker]:
    """Yield the invoker of the reference ``url`` until the context exits, registered as a consumer meanwhile.

    It calls ``providers``, the providers ``url`` names directly, and the
    providers ``registries`` hold, connecting to each in the background.
    The parameters of ``url`` say how: the cluster each set of providers is
    called through, ``cluster``, the applications that provide the
    service, ``provided-by``, the routers that narrow the providers of each
    call, ``router``, the filters each call goes through once, whatever the
    retries, ``reference.filter``, and the settings each attempt on a
    provider takes its filters from, such as ``actives`` and
    ``reference.attempt-filter``. Without registries, ``providers`` are one
    set. Otherwise each registry gives one invoker, and each of
    ``providers`` is one besides; with several, the ``zone-aware`` cluster
    chooses among them by the ``preferred``, ``zone`` and ``weight`` of
    each registry.

    The reference calls from its host, else the local address that reaches
    ``registries``, and is registered as a consumer as
    `dubbo.registry.consumer.register_consumer` describes.

    Raises:
        RuntimeError: ``url`` or a registry belongs to no running application.
        ValueError: A parameter of ``url`` or of a registry is invalid.
        ZookeeperError: A ZooKeeper registry cannot be reached.
    """
    url = url.replace(host=await registered_host(url.host, registries))

    invoker = await _create_invoker(url, definition, providers, registries)
    async with aclosing(invoker), register_consumer(url, definition, registries, generic=generic):
        yield chain_filters(invoker, get_filters(url.get_parameter(REFERENCE_FILTER_KEY, comma_separated, ()), url))


async def _create_invoker(
    url: URL, definition: Service, providers: Sequence[URL], registries: Sequence[URL]
) -> Invoker:
    """Return the invoker of the providers of the reference ``url``, which the caller closes, as `refer` describes."""
    scope = url.scope
    routers = [] if registries else create_routers(url.get_parameter(ROUTER_KEY, comma_separated, DEFAULT_ROUTERS), url)
    # The parameters that choose among registries are not those of the calls.
    consumer = Consumer(
        interface=url.path,
        group=url.parameters.get(GROUP_KEY),
        version=url.parameters.get(VERSION_KEY),
        parameters=url.parameters,
        attributes=url.attributes,
    )
    invokers = []
    async with AsyncExitStack() as stack:
        for registry in registries:
            invoker = await _refer_registry(registry, consumer, definition, url.update_parameters(_choice(registry)))
            stack.push_async_callback(invoker.aclose)
            invokers.append(invoker)
        for provider in providers:
            invoker = await _refer_provider(provider, definition, scope)
            stack.push_async_callback(invoker.aclose)
            invokers.append(invoker)
        # The caller, or the cluster over them, owns them from here.
        stack.pop_all()

    if not registries:
        return await create_cluster(url, StaticDirectory(invokers, routers))
    if len(invokers) == 1:
        return invokers[0]
    return await create_cluster(url.update_parameters({CLUSTER_KEY: ZONE_AWARE_CLUSTER}), StaticDirectory(invokers))


def _choice(registry: URL) -> dict[str, str]:
    """Return the parameters that choose among the invokers of several registries, from those of ``registry``.

    Raises:
        ValueError: ``preferred`` is not a boolean.
    """
    parameters = registry.parameters
    choice = {}
    if registry.get_parameter(PREFERRED_KEY, boolean, False):
        choice[REGISTRY_PREFERRED_KEY] = "true"
    if parameters.get(ZONE_KEY):
        choice[REGISTRY_ZONE_KEY] = parameters[ZONE_KEY]
    if WEIGHT_KEY in parameters:
        choice[WEIGHT_KEY] = parameters[WEIGHT_KEY]

    return choice


async def _refer_registry(registry: URL, consumer: Consumer, definition: Service, url: URL) -> Invoker:
    """Return the invoker of the providers of ``consumer`` that ``registry`` holds, found as its mode says.

    In mode ``all``, the ``zone-aware`` cluster calls those found by
    instance while there are any, else those found by interface. The caller
    closes the invoker.
    """
    mode = registry_mode(registry)
    interface = url.path
    apps = url.get_parameter(PROVIDED_BY_KEY, comma_separated, None)
    routers = url.get_parameter(ROUTER_KEY, comma_separated, DEFAULT_ROUTERS)
    refer = partial(_refer_provider, definition=definition, scope=registry.scope)

    name = f"{interface} in {registry}"
    clusters: list[Invoker] = []
    async with AsyncExitStack() as stack:
        if mode is not RegistryMode.INTERFACE:
            # In mode all, these are called while there are any.
            preferred = url.update_parameters({REGISTRY_PREFERRED_KEY: "true"})
            directory = DynamicDirectory(
                lambda: consumer.watch(subscribe_by_instance(registry, interface, apps), preferred),
                refer,
                name,
                create_routers(routers, preferred),
            )
            clusters.append(await create_cluster(preferred, directory))
            stack.push_async_callback(clusters[-1].aclose)
        if mode is not RegistryMode.INSTANCE:
            directory = DynamicDirectory(
                lambda: consumer.watch(
                    subscribe_by_interface(registry, interface, group=consumer.group, version=consumer.version), url
                ),
                refer,
                name,
                create_routers(routers, url),
            )
            clusters.append(await create_cluster(url, directory))
            stack.push_async_callback(clusters[-1].aclose)
        # The caller, or the zone-aware cluster, owns them from here.
        stack.pop_all()

    if len(clusters) == 1:
        return clusters[0]
    return await create_cluster(url.update_parameters({CLUSTER_KEY: ZONE_AWARE_CLUSTER}), StaticDirectory(clusters))


async def _refer_provider(provider: URL, definition: Service, scope: ApplicationScope) -> Invoker:
    """Return the invoker of ``provider``, each attempt on it through the filters its settings add; the caller closes it."""
    protocol = await get_protocol(provider.protocol, scope)
    invoker = await protocol.refer(provider, definition)
    try:
        return chain_filters(invoker, get_attempt_filters(invoker.url))
    except BaseException:
        await invoker.aclose()
        raise
