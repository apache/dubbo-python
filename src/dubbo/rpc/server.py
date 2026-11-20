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
from typing import Any, Self

import attrs

from dubbo.exceptions import RpcError, Status
from dubbo.url import URL

from .context import incoming
from .definition import Handler, Service, arity, check_handler
from .invocation import Invocation, Invoker, Result

__all__ = ["ServiceInvoker"]

_logger = logging.getLogger(__name__)


@attrs.define(frozen=True, kw_only=True)
class ServiceInvoker(Invoker):
    """Calls the handlers of ``service``, served with ``url``.

    It runs inside the call it serves, so `incoming` is set.

    Raises:
        TypeError: A method of ``service`` has no handler, or one that cannot
            serve it.
    """

    url: URL
    service: Service
    # The handler of each method and how many arguments it takes, by method name.
    _calls: dict[str, tuple[Handler, int]] = attrs.field(init=False, eq=False, repr=False)

    def __attrs_post_init__(self) -> None:
        calls = {}
        for method in self.service.methods:
            where = f"the handler of {self.service.interface}.{method.name}"
            if method.handler is None:
                raise TypeError(f"{where} is missing")
            check_handler(method, method.handler, where)
            calls[method.name] = (method.handler, arity(method))

        object.__setattr__(self, "_calls", calls)

    @classmethod
    def from_implementation(cls, implementation: object, url: URL) -> Self:
        """Return the invoker of ``implementation``, served with ``url``.

        Raises:
            TypeError: As `Service.from_implementation` raises.
        """
        return cls(url=url, service=Service.from_implementation(implementation))

    async def invoke(self, invocation: Invocation) -> Result:
        try:
            handler, count = self._calls[invocation.method]
        except KeyError:
            error = RpcError(Status.UNIMPLEMENTED, f"{self.service.interface} has no method {invocation.method!r}")
            return Result(error=error)

        # Arguments come from the other side, which may not share the contract.
        if len(invocation.arguments) != count:
            error = RpcError(
                Status.INVALID_ARGUMENT,
                f"{invocation.method}() takes {count} arguments, not {len(invocation.arguments)}",
            )
            return Result(error=error)

        response_attachments = incoming().response_attachments

        try:
            value: Any = await handler(*invocation.arguments)
        except Exception as error:
            # An RpcError is a status the handler chose; anything else is a failure its caller cannot locate.
            if not isinstance(error, RpcError):
                _logger.exception(
                    "The method %s of %s raised; its caller receives the error",
                    invocation.method,
                    self.service.interface,
                )
            return Result(error=error, attachments=response_attachments)

        return Result(value=value, attachments=response_attachments)

    async def aclose(self) -> None:
        pass
