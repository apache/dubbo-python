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
from typing import Self, TypeVar

import attrs

from dubbo.exceptions import RpcError, Status

# Only for annotations: protobuf stays optional.
if typing.TYPE_CHECKING:
    from google.protobuf.message import Message

__all__ = ["ErrorDetail", "TripleError"]

M = TypeVar("M", bound="Message")

_TYPE_URL_PREFIX = "type.googleapis.com/"


@attrs.define(frozen=True, kw_only=True)
class ErrorDetail:
    """A message that tells more about why a call failed, held as a ``google.protobuf.Any``.

    Attributes:
        type_url: Names the type of the message, as in
            ``type.googleapis.com/google.rpc.ErrorInfo``.
        value: The message, serialized.
    """

    type_url: str
    value: bytes

    @classmethod
    def from_message(cls, message: "Message") -> Self:
        """Hold a protobuf message."""
        return cls(type_url=_TYPE_URL_PREFIX + message.DESCRIPTOR.full_name, value=message.SerializeToString())

    def unpack(self, message_type: type[M]) -> M | None:
        """Return the message as a ``message_type``, or ``None`` when it is of another type.

        Raises:
            google.protobuf.message.DecodeError: ``value`` does not hold a
                ``message_type``.
        """
        if self.type_url.rpartition("/")[2] != message_type.DESCRIPTOR.full_name:
            return None
        return message_type.FromString(self.value)


class TripleError(RpcError):
    """A Triple call failed with a status and details, as the rich error model of gRPC carries them.

    A handler raises it to send the details along; the caller receives an
    equal error. Triple carries the details; other protocols carry the
    status and message alone.

    Attributes:
        details: Messages that tell programs more, such as which field of
            the request is invalid.
    """

    def __init__(self, status: Status, message: str = "", *, details: Sequence[ErrorDetail] = ()) -> None:
        super().__init__(status, message)
        self.details = tuple(details)
