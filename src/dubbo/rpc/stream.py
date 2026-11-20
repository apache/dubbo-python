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

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import TracebackType
from typing import Generic, Self, TypeVar

from dubbo.exceptions import EndOfStream

__all__ = ["BidiStream", "ClientStream", "ReceiveStream", "SendStream", "ServerStream", "Stream"]

T_contra = TypeVar("T_contra", contravariant=True)
T_co = TypeVar("T_co", covariant=True)


class SendStream(ABC, Generic[T_contra]):
    """Messages one side of a call sends."""

    @abstractmethod
    async def send(self, message: T_contra) -> None:
        """Send ``message``, waiting while the other side cannot take more.

        Raises:
            RpcError: The call failed.
        """


class ReceiveStream(ABC, Generic[T_co]):
    """Messages one side of a call receives; ``async for`` reads them all."""

    @abstractmethod
    async def receive(self) -> T_co:
        """Return the next message.

        Raises:
            EndOfStream: The other side has ended its messages.
            RpcError: The call failed.
        """

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> T_co:
        try:
            return await self.receive()
        except EndOfStream:
            raise StopAsyncIteration from None


class Stream(SendStream[T_contra], ReceiveStream[T_co]):
    """Messages in both directions: sends ``T_contra`` and receives ``T_co``."""

    @abstractmethod
    async def end(self) -> None:
        """End the messages this side sends; receiving continues."""


class _Call(ABC):
    """A streaming call as its caller holds it; leaving the ``async with`` block ends it.

    A streaming call has no timeout; bound it with ``anyio.fail_after``,
    whose deadline travels to a ``tri`` provider as ``grpc-timeout``.
    Cancelling the task that awaits a call cancels the call.
    """

    @property
    @abstractmethod
    def response_attachments(self) -> Mapping[str, str | bytes]:
        """Attachments the server sent back, complete once the call has ended.

        Callers read them from `dubbo.outgoing`, where the call leaves them
        when its block exits.
        """

    async def __aenter__(self) -> Self:
        return self

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """End the call, cancelling it if it still runs."""


class ServerStream(ReceiveStream[T_co], _Call, ABC):
    """A server-streaming call as its caller holds it.

    The caller receives the responses::

        async with users.watch(query) as events:
            async for event in events: ...
    """


class ClientStream(Stream[T_contra, T_co], _Call, ABC):
    """A client-streaming call as its caller holds it.

    The caller sends the requests, ends them, then receives the one response::

        async with users.upload() as stream:
            await stream.send(chunk)
            await stream.end()
            total = await stream.receive()

    A handler normally answers after the requests end, but may answer
    earlier.
    """


class BidiStream(Stream[T_contra, T_co], _Call, ABC):
    """A bidirectional streaming call as its caller holds it.

    The caller sends requests and receives responses in any order::

        async with users.chat() as stream:
            await stream.send(question)
            answer = await stream.receive()
    """
