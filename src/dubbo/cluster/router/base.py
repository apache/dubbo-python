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

import typing
from collections.abc import Sequence
from typing import Self, cast

from dubbo.constants import REMOTE_APPLICATION_KEY
from dubbo.extension import Resource, extension_point, extensions
from dubbo.rpc.invocation import Invocation, Invoker
from dubbo.url import PROVIDER_URL, URL

__all__ = ["Router", "create_routers", "providers_by_application", "published"]


@extension_point("apache_dubbo.router")
class Router(Resource, typing.Protocol):
    """Narrows the providers a call of a reference may go to, before its cluster chooses among them.

    Implement ``__init__(url)``, ``notify`` and ``route``, with
    ``__aenter__`` and ``aclose`` when it follows something, and install the
    class under the entry point group ``apache_dubbo.router``; ``router``
    (``ReferenceConfig.routers``) names the routers of a reference in order,
    ``tag`` then ``condition`` by default, and they act as one
    ``RouterChain``.

    One is created with the URL of the reference for each of its
    directories: the providers of each registry, once per discovery mode,
    or, without registries, the providers its ``urls`` name. Its directory
    enters and closes it. The attributes of ``url`` hold the application
    scope under ``APPLICATION_SCOPE`` and, if the application has one, the
    URL of its configuration center under ``CONFIG_CENTER_URL``, whose rules
    ``RuleWatch`` follows.

    ``notify`` gets each new list of providers before calls are routed
    among them; ``route`` runs on every attempt, for many calls at once.
    Both run in the event loop and must not block; work that depends only
    on the providers belongs in ``notify``.
    """

    def __init__(self, url: URL) -> None: ...

    def notify(self, invokers: Sequence[Invoker]) -> None:
        """Take the providers of the reference, which changed, before calls are routed among them."""
        ...

    def route(self, invokers: Sequence[Invoker], invocation: Invocation) -> Sequence[Invoker]:
        """Return those of ``invokers`` that ``invocation`` may go to, possibly none.

        Returning ``invokers`` itself when it narrows nothing keeps the
        sequence the same object while the providers do not change.
        """
        ...

    async def aclose(self) -> None:
        """Stop following it."""
        ...

    async def __aenter__(self) -> Self:
        """Start following what the routing depends on, such as rules."""
        ...


def create_routers(names: Sequence[str], url: URL) -> list[Router]:
    """Create the routers ``names`` names, in order, each with the URL of the reference; the directory that takes them closes them.

    Raises:
        ExtensionError: A router is not installed.
    """
    return [extensions.get(Router, name)(url) for name in names]


def published(invoker: Invoker) -> URL:
    """Return the URL the provider of ``invoker`` published, which the settings of the calls do not change."""
    return cast(URL, invoker.url.attributes.get(PROVIDER_URL, invoker.url))


def providers_by_application(invokers: Sequence[Invoker]) -> dict[str | None, list[Invoker]]:
    """Return ``invokers`` in order by the application of their providers, ``None`` for those that name none."""
    applications: dict[str | None, list[Invoker]] = {}
    for invoker in invokers:
        applications.setdefault(invoker.url.parameters.get(REMOTE_APPLICATION_KEY), []).append(invoker)
    return applications
