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

"""How a registry gives a reference the providers it holds, selected and completed, and holds the reference as a consumer."""

from collections.abc import AsyncGenerator, AsyncIterator, Callable, Collection, Iterable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

import anyio
import attrs

from dubbo.cluster.configurator import Overrides
from dubbo.config import RegistryMode
from dubbo.constants import (
    APPLICATION_KEY,
    CATEGORY_KEY,
    CHECK_KEY,
    CONSUMERS_CATEGORY,
    DUBBO_VERSION_KEY,
    GENERIC_KEY,
    GROUP_KEY,
    INTERFACE_KEY,
    METHODS_KEY,
    PROVIDERS_CATEGORY,
    RELEASE_KEY,
    REMOTE_APPLICATION_KEY,
    SIDE_KEY,
    TAG_KEY,
    TIMESTAMP_KEY,
    VERSION_KEY,
)
from dubbo.extension import extensions
from dubbo.protocol import Protocol
from dubbo.rpc.definition import Service
from dubbo.url import CONFIG_CENTER_URL, PROVIDER_URL, URL
from dubbo.utils import Latest
from dubbo.utils.converters import is_true

from .base import get_interface_registry, registry_mode
from .registration import published_parameters, registered_parameters, registers, simplified

__all__ = ["Consumer", "register_consumer"]

_ENABLED_KEY = "enabled"
_DISABLED_KEY = "disabled"
# What a provider says about itself, which the parameters of the calls do not replace.
_PROVIDER_FIRST = (
    GROUP_KEY,
    VERSION_KEY,
    TAG_KEY,
    METHODS_KEY,
    RELEASE_KEY,
    DUBBO_VERSION_KEY,
    TIMESTAMP_KEY,
    _ENABLED_KEY,
    _DISABLED_KEY,
)
# Parameters of the URL of a reference that its registered consumer URL publishes.
_CONSUMER_PUBLISHED_KEYS = (APPLICATION_KEY, GROUP_KEY, VERSION_KEY, TAG_KEY)
# Parameters that simplified consumer URLs keep.
_CONSUMER_KEYS = frozenset(
    {APPLICATION_KEY, VERSION_KEY, GROUP_KEY, DUBBO_VERSION_KEY, RELEASE_KEY, CATEGORY_KEY, CHECK_KEY}
)


@attrs.define(frozen=True, kw_only=True)
class Consumer:
    """The service a reference calls, which selects and completes the URLs of providers.

    Attributes:
        interface: Interface name of the service.
        group: Group of the service; ``*`` accepts any, and commas separate several.
        version: Version of the service; ``*`` accepts any.
        parameters: Parameters of the calls, which provider URLs take.
        attributes: Attributes of the reference, which provider URLs take.
    """

    interface: str
    group: str | None
    version: str | None
    parameters: Mapping[str, str]
    attributes: Mapping[str, object] = attrs.field(factory=dict)

    def prepare(self, provider: URL) -> URL | None:
        """Return the URL to call ``provider`` with, or ``None`` if it does not serve this service.

        The URL keeps the provider's address and path. Its parameters are the
        parameters of the calls, over those that providers publish for their
        consumers, such as ``timeout`` and ``token``. Where the provider says
        what it is, such as its group and version, the provider's value wins;
        the tag is the provider's alone. Its application becomes
        ``remote.application``. The attribute ``PROVIDER_URL`` keeps
        ``provider`` as it is, with every parameter.
        """
        if not self._accepts(provider):
            return None

        offered = provider.parameters
        parameters = published_parameters(offered)
        parameters |= {key: value for key, value in self.parameters.items() if key != TAG_KEY}
        parameters |= {key: offered[key] for key in _PROVIDER_FIRST if key in offered}
        if APPLICATION_KEY in offered:
            parameters[REMOTE_APPLICATION_KEY] = offered[APPLICATION_KEY]

        return URL(
            protocol=provider.protocol,
            host=provider.host,
            port=provider.port,
            path=provider.path or self.interface,
            parameters=parameters,
            attributes={**self.attributes, PROVIDER_URL: provider},
        )

    @asynccontextmanager
    async def watch(
        self, subscription: AbstractAsyncContextManager[AsyncIterator[list[URL]]], url: URL
    ) -> AsyncGenerator[AsyncIterator[list[URL]]]:
        """Watch the URLs to call the providers of this service with, among the provider URLs of ``subscription``.

        The override rules of the configuration center of ``url``, the URL of
        the reference, apply to them, if it has one, and a change of the
        rules gives the URLs again. A provider whose URL, after the rules,
        sets ``disabled`` true, or else ``enabled`` false, is left out.
        """
        prepare = self._preparing()
        if CONFIG_CENTER_URL not in url.attributes:
            async with subscription as snapshots:
                yield ([url for url in prepare(urls) if _enabled(url)] async for urls in snapshots)
            return

        latest: Latest[list[URL]] = Latest()
        prepared: list[URL] | None = None

        def publish() -> None:
            if prepared is not None:
                latest.publish([url for url in overrides.configure(prepared) if _enabled(url)])

        async def receive(snapshots: AsyncIterator[list[URL]]) -> None:
            nonlocal prepared
            try:
                async for urls in snapshots:
                    prepared = prepare(urls)
                    publish()
            except Exception as error:
                latest.close(error)
            else:
                latest.close()

        overrides = Overrides(url, "consumer", publish)
        async with overrides, subscription as snapshots, anyio.create_task_group() as task_group:
            task_group.start_soon(receive, snapshots)
            yield aiter(latest)
            task_group.cancel_scope.cancel()

    def _preparing(self) -> Callable[[list[URL]], list[URL]]:
        """Return what prepares the providers of each snapshot, reusing what it prepared for the snapshot before."""
        last: dict[URL, URL | None] = {}

        def prepare(urls: list[URL]) -> list[URL]:
            nonlocal last
            last = {url: last[url] if url in last else self.prepare(url) for url in urls}
            return [prepared for url in urls if (prepared := last[url]) is not None]

        return prepare

    def _accepts(self, provider: URL) -> bool:
        parameters = provider.parameters
        if (parameters.get(INTERFACE_KEY) or provider.path) != self.interface:
            return False
        if parameters.get(CATEGORY_KEY, PROVIDERS_CATEGORY) != PROVIDERS_CATEGORY:
            return False
        if provider.host is None or provider.protocol not in extensions.names(Protocol):
            return False

        return _group_accepts(self.group, parameters.get(GROUP_KEY)) and (
            self.version == "*" or (self.version or "") == parameters.get(VERSION_KEY, "")
        )


def _enabled(url: URL) -> bool:
    """Return whether the provider ``url`` takes calls: by ``disabled`` if it has one, else by ``enabled``, true when absent."""
    parameters = url.parameters
    if _DISABLED_KEY in parameters:
        return not is_true(parameters[_DISABLED_KEY])
    return is_true(parameters.get(_ENABLED_KEY, "true"))


def _group_accepts(wanted: str | None, group: str | None) -> bool:
    if wanted == "*":
        return True
    if wanted and "," in wanted:
        return (group or "") in wanted.split(",")
    return (wanted or "") == (group or "")


@asynccontextmanager
async def register_consumer(
    url: URL, definition: Service, registries: Iterable[URL], *, generic: str | None
) -> AsyncGenerator[None]:
    """Register the reference ``url`` as a consumer until the context exits.

    It is registered in the ``consumers`` category of those of
    ``registries`` that register by interface and do not set ``register``
    to false; a registry URL with ``simplified=true`` gets only the
    parameters that identify the consumer. A reference of a ``generic``
    mode, which calls methods by name without a contract, is registered
    with that mode, such as ``generic=true``, and no ``methods``.
    """
    consumer = _consumer_url(url, [method.name for method in definition.methods], generic=generic)
    async with AsyncExitStack() as stack:
        for registry in registries:
            if registers(registry) and registry_mode(registry) is not RegistryMode.INSTANCE:
                interface_registry = await get_interface_registry(registry)
                await stack.enter_async_context(
                    interface_registry.register(_registered_consumer_url(consumer, registry))
                )

        yield


def _consumer_url(url: URL, methods: Collection[str], *, generic: str | None) -> URL:
    """Return the URL that registries publish for the reference ``url``, in the ``consumers`` category."""
    parameters = {key: value for key, value in url.parameters.items() if key in _CONSUMER_PUBLISHED_KEYS}
    parameters |= registered_parameters(methods)
    if generic is not None:
        del parameters[METHODS_KEY]
        parameters[GENERIC_KEY] = generic
    parameters |= {SIDE_KEY: "consumer", CATEGORY_KEY: CONSUMERS_CATEGORY, CHECK_KEY: "false", INTERFACE_KEY: url.path}

    return URL(protocol="consumer", host=url.host, path=url.path, parameters=parameters)


def _registered_consumer_url(url: URL, registry: URL) -> URL:
    """Return ``url`` as ``registry`` takes it: whole, or simplified to what identifies the consumer."""
    if not simplified(registry):
        return url

    return url.replace(parameters={key: value for key, value in url.parameters.items() if key in _CONSUMER_KEYS})
