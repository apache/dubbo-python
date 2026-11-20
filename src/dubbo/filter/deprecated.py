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

import logging
from typing import cast

from dubbo.constants import DEPRECATED_KEY
from dubbo.rpc.invocation import Invocation, Invoke, Result
from dubbo.url import URL
from dubbo.utils.converters import is_true

from .base import Filter

__all__ = ["DeprecatedFilter"]

_logger = logging.getLogger(__name__)


class DeprecatedFilter(Filter):
    """Logs a warning the first time the application calls a method that the provider ``url`` deprecates.

    A method is deprecated when ``{method}.deprecated``, else
    ``deprecated``, reads ``true``. The methods warned of are kept in the
    ``ApplicationScope.state`` of the application, by service and method.

    Raises:
        RuntimeError: No application made ``url``.
    """

    def __init__(self, url: URL) -> None:
        self._warned = _warned(url)
        self._default = url.get_parameter(DEPRECATED_KEY, is_true, False)
        self._deprecated = url.get_method_parameters(DEPRECATED_KEY, is_true)
        self._service = url.service_key
        self._address = url.address

    async def invoke(self, call_next: Invoke, invocation: Invocation) -> Result:
        method = invocation.method
        if self._deprecated.get(method, self._default) and (self._service, method) not in self._warned:
            self._warned.add((self._service, method))
            _logger.warning("Calling %s.%s, which its provider at %s deprecates", self._service, method, self._address)

        return await call_next(invocation)


def _warned(url: URL) -> set[tuple[str, str]]:
    return cast(set[tuple[str, str]], url.scope.state.setdefault(DeprecatedFilter, set()))
