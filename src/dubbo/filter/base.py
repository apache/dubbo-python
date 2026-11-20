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

from dubbo.extension import extension_point, extensions
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL

__all__ = [
    "ATTEMPT_FILTER_KEY",
    "Filter",
    "get_filters",
]

# The URL parameter that names, separated by commas, the filters each attempt of a call runs through.
ATTEMPT_FILTER_KEY = "reference.attempt-filter"


@extension_point("apache_dubbo.filter")
class Filter(typing.Protocol):
    """Runs around the calls of a service or a reference.

    Implement ``__init__(url)`` and ``invoke``, and install the class under
    the entry point group ``apache_dubbo.filter``; its name goes where the
    filter runs:

    - ``service.filter`` (``ServiceConfig.filters``): around each call the
      service serves, inside the context of the handler, so that
      `dubbo.incoming` works;
    - ``reference.filter`` (``ReferenceConfig.filters``): around each call
      of the reference, once whatever the retries, in the caller's task;
    - ``reference.attempt-filter`` (``ReferenceConfig.attempt_filters``):
      around each attempt on one provider.

    One is created with the URL of each invoker it runs around, and created
    again with the URL the override rules change, so it reads its settings
    once and keeps nothing of its own across calls: what calls or filters
    share goes in ``url.scope.state``. It holds nothing and is never
    closed. ``invoke`` runs in the event loop, for many calls at once.

    A filter may change the invocation, return a result of its own without
    calling ``call_next``, or change the result afterwards. It fails a call
    by returning ``Result(error=RpcError(...))``; an exception it raises is
    a failure of the framework, which the caller sees raised, and the
    caller of a served call as ``INTERNAL``::

        class Timing(Filter):
            def __init__(self, url: URL) -> None:
                self._service = url.path

            async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
                start = time.monotonic()
                try:
                    return await call_next(invocation)
                finally:
                    observe(self._service, invocation.method, time.monotonic() - start)

    On the calling side, a streaming call returns once it has opened; on the
    serving side, once its handler has returned.
    """

    def __init__(self, url: URL) -> None: ...

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        """Run around one call; ``call_next`` makes it through the rest of the chain."""
        ...


def get_filters(names: Sequence[str], url: URL) -> list[Filter]:
    """Return the filters ``names`` names, in order, each created with ``url``."""
    return [extensions.get(Filter, name)(url) for name in names]
