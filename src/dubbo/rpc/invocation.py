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
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import attrs
from multidict import MultiDict

from dubbo.extension import Resource
from dubbo.url import URL

from .definition import Method

__all__ = ["Invocation", "Invoke", "Invoker", "Result"]


@attrs.define(kw_only=True)
class Invocation:
    """One call, as it passes from a caller through filters and clusters to a protocol, or from a server through filters to a handler.

    The same invocation goes to every attempt of a call, so what changes it
    for one attempt changes a copy made by ``attrs.evolve``, with a copy of
    ``attachments`` when it changes them.

    Attributes:
        interface: Interface name, such as ``"com.example.UserService"``.
        method: Name of the method on the wire, such as ``"getUser"``.
        arguments: Arguments in parameter order. On the serving side a
            streaming call carries its stream last: ``(request, stream)`` for
            a server stream, ``(stream,)`` for the others.
        attachments: Attachments to send, or on the serving side those
            received; a key may repeat. Keys ending in ``-bin`` carry bytes.
        definition: The method called. A generic call defines it from the
            call: unary, with an argument of any type for each argument given,
            returning any value.
        generic: The mode of a generic call, such as ``"true"``: one made
            without the contract of the service, its arguments and result
            plain data, such as dicts and lists, as `dubbo.GenericService`
            makes it. ``None`` for a call of the contract.
    """

    interface: str
    method: str
    definition: Method
    arguments: tuple[Any, ...] = ()
    attachments: MutableMapping[str, str | bytes] = attrs.field(factory=MultiDict)
    generic: str | None = None


@attrs.define(kw_only=True)
class Result:
    """How a call ended.

    Attributes:
        value: What the handler returned. On the calling side of a streaming
            call, the call itself instead: a `ServerStream`, `ClientStream`
            or `BidiStream`.
        error: Why the call failed, ``None`` when it succeeded: what the
            handler raised, or on the calling side what the caller will see
            raised, such as an `RpcError` of ``UNAVAILABLE``.
        attachments: Response attachments of a unary call, or of a streaming
            call that failed to start. A started streaming call carries them
            as its `response_attachments` instead.
    """

    value: Any = None
    error: Exception | None = None
    attachments: MutableMapping[str, str | bytes] = attrs.field(factory=MultiDict)


# Makes a call and returns how it ended, as `Invoker.invoke` does.
Invoke = Callable[[Invocation], Awaitable[Result]]


class Invoker(Resource, typing.Protocol):
    """Makes the calls of one service: a handler, one provider, a cluster of providers, or filters around one of these.

    `Protocol.refer` and `create_cluster` create the invokers of callers,
    `ServiceInvoker` that of a handler, and `chain_filters` wraps them;
    whoever creates one closes it, and closing it closes those it wraps.
    ``invoke`` runs concurrently for many calls in the event loop.
    """

    @property
    def url(self) -> URL:
        """The URL it calls or serves with, whose parameters configure it."""
        ...

    @property
    def available(self) -> bool:
        """Whether it takes calls now; an invoker that does not say otherwise always does.

        Clusters prefer the available ones but call one that is not when none is.
        """
        return True

    async def invoke(self, invocation: Invocation) -> Result:
        """Make the call and return how it ended.

        Every failure of the call comes back in `Result.error`: what the
        handler raised, a timeout, no provider, a lost connection. ``invoke``
        raises only for a bug, or for the cancellation of the calling task,
        which it lets through.
        """
        ...

    async def aclose(self) -> None:
        """Release what the invoker holds, including what the invokers it wraps hold.

        An invoker that holds nothing returns at once.
        """
        ...
