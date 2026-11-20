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

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import TracebackType

import attrs
from multidict import MultiDict, MultiDictProxy

from dubbo.constants import (
    DUBBO_VERSION_KEY,
    FORCE_TAG_KEY,
    GROUP_KEY,
    INTERFACE_KEY,
    PATH_KEY,
    TAG_KEY,
    TIMEOUT_KEY,
    TOKEN_KEY,
    VERSION_KEY,
)

__all__ = ["IncomingCall", "OutgoingCall", "attachments_to_send", "incoming", "outgoing", "record_response", "serving"]


@attrs.define(frozen=True, kw_only=True)
class IncomingCall:
    """The call a service handler is serving.

    Attributes:
        attachments: Attachments the caller sent, with every value of a
            repeated key.
        response_attachments: Attachments to send back to the caller; `add`
            gives a key another value.
        peer: ``host:port`` of the caller, an IPv6 host in brackets; ``None`` for an in-process call.
    """

    attachments: MultiDictProxy[str | bytes]
    response_attachments: MultiDict[str | bytes] = attrs.field(factory=MultiDict)
    peer: str | None = None


@attrs.define(kw_only=True)
class OutgoingCall:
    """Calls made inside an `outgoing` block.

    Attributes:
        attachments: Attachments each call in the block sends.
        response_attachments: Attachments the last call to finish in the block
            received; empty until one finishes.
    """

    attachments: MultiDictProxy[str | bytes]
    response_attachments: MultiDictProxy[str | bytes] = attrs.field(factory=lambda: MultiDictProxy(MultiDict()))


# Attachments of one call only, which the calls its handler makes do not inherit: those of Dubbo for one provider,
# HTTP fields of one connection or request, and credentials.
_NOT_INHERITED = frozenset({
    PATH_KEY, INTERFACE_KEY, GROUP_KEY, VERSION_KEY, DUBBO_VERSION_KEY, TOKEN_KEY, TIMEOUT_KEY, "_to", "async",
    TAG_KEY, FORCE_TAG_KEY,
    "accept", "accept-charset", "accept-datetime", "accept-encoding", "accept-language",
    "access-control-request-headers", "access-control-request-method", "authorization", "cache-control",
    "connection", "content-length", "content-md5", "content-type", "cookie", "date", "dnt", "expect", "forwarded",
    "from", "host", "http2-settings", "if-match", "if-modified-since", "if-none-match", "if-range",
    "if-unmodified-since", "keep-alive", "max-forwards", "origin", "pragma", "proxy-authorization",
    "proxy-connection", "range", "referer", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "sec-fetch-user",
    "te", "trailer", "transfer-encoding", "upgrade", "upgrade-insecure-requests", "user-agent",
})  # fmt: skip

_incoming: ContextVar[IncomingCall] = ContextVar("dubbo.incoming")
_outgoing: ContextVar[OutgoingCall | None] = ContextVar("dubbo.outgoing", default=None)


def incoming() -> IncomingCall:
    """Return the call the running service handler is serving.

    Raises:
        LookupError: No service handler is running.
    """
    try:
        return _incoming.get()
    except LookupError:
        raise LookupError("dubbo.incoming() is available only while a service handler runs") from None


@contextmanager
def outgoing(attachments: Mapping[str, str | bytes] | None = None, *, inherit: bool = True) -> Generator[OutgoingCall]:
    """Add attachments to the calls made inside the block.

    A call sends the attachments it inherits, then ``attachments``; the inner
    value wins on equal keys. Keys ending in ``-bin`` carry bytes, other keys
    printable ASCII text. A block inherits from the enclosing block or, at
    the top, from the call the running handler serves, so attachments pass
    along a chain of services. Attachments of one call only are never
    inherited: ``token``, ``timeout``, ``dubbo.tag``, the identity of the
    service called, and HTTP fields such as ``authorization``.
    ``inherit=False`` starts from nothing.

    The last call to finish in the block, innermost block only, leaves its
    response attachments on the yielded `OutgoingCall`::

        with dubbo.outgoing({"operator": "alice"}) as call:
            await users.rename(1, "b")
        call.response_attachments
    """
    merged = attachments_to_send() if inherit else MultiDict()
    merged.update(attachments or {})
    call = OutgoingCall(attachments=MultiDictProxy(merged))

    token = _outgoing.set(call)
    try:
        yield call
    finally:
        _outgoing.reset(token)


def attachments_to_send() -> MultiDict[str | bytes]:
    """Return the attachments a call made now sends."""
    call = _outgoing.get()
    if call is not None:
        return MultiDict(call.attachments)

    try:
        received = _incoming.get().attachments
    except LookupError:
        return MultiDict()

    return MultiDict((key, value) for key, value in received.items() if key.lower() not in _NOT_INHERITED)


def record_response(attachments: Mapping[str, str | bytes]) -> None:
    """Leave the response attachments of a finished call on the innermost `outgoing` block."""
    call = _outgoing.get()
    if call is not None:
        call.response_attachments = MultiDictProxy(MultiDict(attachments))


class _Serving:
    __slots__ = ("_call", "_tokens")

    def __init__(self, call: IncomingCall) -> None:
        self._call = call

    def __enter__(self) -> IncomingCall:
        self._tokens = (_incoming.set(self._call), _outgoing.set(None))
        return self._call

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        incoming_token, outgoing_token = self._tokens
        _outgoing.reset(outgoing_token)
        _incoming.reset(incoming_token)


def serving(attachments: Mapping[str, str | bytes], *, peer: str | None) -> _Serving:
    """Return a context manager that runs its block as serving a call that sent ``attachments``.

    A server runs each handler inside it, so that `incoming` returns the
    call. Calls the block makes inherit from this call alone, never from the
    `outgoing` blocks of whoever started the block, such as the caller of an
    in-process call.
    """
    return _Serving(IncomingCall(attachments=MultiDictProxy(MultiDict(attachments)), peer=peer))
