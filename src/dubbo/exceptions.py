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

import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

__all__ = ["DubboError", "EndOfStream", "RemoteError", "RpcError", "Status"]


class DubboError(Exception):
    """Base class for framework-defined exceptions."""


class EndOfStream(DubboError):
    """Raised by `ReceiveStream.receive` once the other side has ended its messages; ``async for`` stops on it."""

    def __init__(self) -> None:
        super().__init__("the other side ended what it sends")


class Status(enum.IntEnum):
    """Why a call ended: the gRPC status codes, which every protocol maps to its wire format.

    The framework itself ends a call with:

    - ``UNAVAILABLE``: no provider could take it: none was found, the
      connection failed or closed, or a limit such as ``executes``, ``tps``
      or ``actives`` was reached. The default ``failover`` cluster retries
      only this status, on another provider.
    - ``DEADLINE_EXCEEDED``: the ``timeout`` of a unary call passed.
    - ``PERMISSION_DENIED``: the call lacks the provider's ``token``.
    - ``UNIMPLEMENTED``: the provider has no such method.
    - ``UNKNOWN``: the handler raised an exception that names no status.
    """

    OK = 0
    CANCELLED = 1
    UNKNOWN = 2
    INVALID_ARGUMENT = 3
    DEADLINE_EXCEEDED = 4
    NOT_FOUND = 5
    ALREADY_EXISTS = 6
    PERMISSION_DENIED = 7
    RESOURCE_EXHAUSTED = 8
    FAILED_PRECONDITION = 9
    ABORTED = 10
    OUT_OF_RANGE = 11
    UNIMPLEMENTED = 12
    INTERNAL = 13
    UNAVAILABLE = 14
    DATA_LOSS = 15
    UNAUTHENTICATED = 16


class RpcError(DubboError):
    """A call failed with a status.

    A handler raises it to fail its call with ``status``; the caller receives
    an `RpcError` of the same status and message. Over a format of Java
    objects, such as Dubbo with ``hessian2``, it arrives as a `RemoteError` of
    ``org.apache.dubbo.rpc.RpcException``, of the same status where that
    exception has a code for it, and another exception as a `RemoteError` of
    ``java.lang.RuntimeException``; otherwise another exception arrives as
    `Status.UNKNOWN`. A protocol may carry more about the failure in an error
    of its own, such as the details of `dubbo.protocol.triple.TripleError`.

    Attributes:
        status: Why the call failed.
        message: Description for people.
    """

    def __init__(self, status: Status, message: str = "") -> None:
        super().__init__(status, message)
        self.status = status
        self.message = message

    def __str__(self) -> str:
        return f"{self.status.name}: {self.message}" if self.message else self.status.name


class RemoteError(RpcError):
    """An exception the code of the other side raised, of a class it names, such as ``java.lang.IllegalStateException``.

    A caller receives it for an exception the method of a provider raised;
    a handler raises it to fail its call with an exception of
    ``class_name``. It is the answer of the method, so a cluster never
    retries it.

    Attributes:
        class_name: The class of the exception, as its language names it.
        fields: The other fields of the exception, such as ``code``, or the
            ``cause`` and ``stackTrace`` of a Java throwable.
    """

    def __init__(
        self,
        class_name: str,
        message: str = "",
        *,
        fields: Mapping[str, Any] | None = None,
        status: Status = Status.UNKNOWN,
    ) -> None:
        super().__init__(status, message)
        self.class_name = class_name
        self.fields: Mapping[str, Any] = MappingProxyType(dict(fields or {}))

    def __str__(self) -> str:
        return f"{self.class_name}: {self.message}" if self.message else self.class_name
