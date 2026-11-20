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

"""The services a Triple server serves, and the route of each of their methods."""

import attrs

from dubbo.protocol.generic import builtin_methods
from dubbo.protocol.served import ServedService
from dubbo.rpc.definition import Method, Service
from dubbo.rpc.invocation import Invoke
from dubbo.serialization import JavaSerialization, Serialization

from .messages import MethodMessages, method_messages

__all__ = ["Route", "RouteKey", "get_routes"]

# A route is found by the path, group and version of a request.
RouteKey = tuple[bytes, bytes, bytes]


@attrs.define(frozen=True, kw_only=True)
class Route:
    """How to serve one method of an exported service, made once when the service is exported.

    Attributes:
        messages: How the values of the method travel. Making them checks
            that the format can carry the method, so a method it cannot
            carry fails the export instead of every call.
        subtype: Content-subtype of the messages, compared with each request's.
        invoke: Serves the calls of the method.
    """

    service: ServedService
    method: Method
    messages: MethodMessages
    subtype: bytes
    invoke: Invoke


def get_routes(service: ServedService, definition: Service, serialization: Serialization) -> dict[RouteKey, Route]:
    """Return the routes of the methods of ``definition``, served by ``service`` in ``serialization``.

    In a format of Java objects, the service also serves the
    `dubbo.protocol.generic.builtin_methods`.

    Raises:
        TypeError: ``serialization`` cannot carry a method.
    """
    group, version = service.group.encode(), service.version.encode()

    invoke = service.invoker.invoke
    methods: list[tuple[Method, Invoke]] = [(method, invoke) for method in definition.methods]
    if isinstance(serialization, JavaSerialization):
        methods += builtin_methods(definition, invoke, serialization)

    routes: dict[RouteKey, Route] = {}
    for method, serve in methods:
        path = f"/{definition.interface}/{method.name}".encode()
        messages = method_messages(serialization, method)
        routes[path, group, version] = Route(
            service=service,
            method=method,
            messages=messages,
            subtype=messages.content_subtype.encode("ascii"),
            invoke=serve,
        )

    return routes
