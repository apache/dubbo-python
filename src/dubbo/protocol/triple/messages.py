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

"""How the values of a method travel as Triple messages: in the format itself, or wrapped."""

from collections.abc import Callable, Sequence
from typing import Any

import attrs
from google.protobuf.message import Message

from dubbo.rpc.definition import Method
from dubbo.serialization import Codec, JavaSerialization, Serialization
from dubbo.serialization.protobuf import ProtobufSerialization
from dubbo.url import URL

__all__ = ["MethodMessages", "method_codecs", "method_messages"]


@attrs.define(frozen=True, kw_only=True)
class MethodMessages:
    """How the values of one method travel as Triple messages, made once for each method.

    An error travels as the gRPC status of the call. In the wrapped messages
    of a format of Java objects, an exception the method threw may instead
    travel as the response message, flagged by ``tri-exception-code``.

    Attributes:
        content_subtype: Names the format of the messages in their content
            type, such as ``proto``.
        request: Codec of a request: the values of all the parameters.
        response: Codec of a response: the one value returned.
        exception: Codec of a response that is an exception the method
            threw, which encodes any exception and decodes as the error the
            caller receives; ``None`` where exceptions travel only as
            statuses.
    """

    content_subtype: str
    request: Codec[tuple[Any, ...]]
    response: Codec[tuple[Any, ...]]
    exception: Codec[tuple[Any, ...]] | None = None


def method_messages(serialization: Serialization, method: Method) -> MethodMessages:
    """Return how the values of ``method`` travel in ``serialization``.

    The values of a format of Java objects, such as ``hessian2``, each travel
    wrapped in a protobuf message, unless the method takes and returns
    protobuf messages, which travel as themselves; the values of another
    format, such as protobuf, travel as its messages.

    Raises:
        TypeError: ``serialization`` cannot carry the request or response of ``method``.
    """
    # shortcut: only formats of Java objects travel wrapped; one wrapped without Java types needs the format to say so.
    if isinstance(serialization, JavaSerialization):
        if not _takes_messages(method):
            # Imported here, as the wrapper builds on this module.
            from .wrapper import wrapped_messages

            return wrapped_messages(serialization, method)
        serialization = _PROTOBUF

    request, response = method_codecs(serialization.codec, method)
    return MethodMessages(content_subtype=serialization.content_subtype, request=request, response=response)


_PROTOBUF = ProtobufSerialization(URL(protocol="tri"))


def _takes_messages(method: Method) -> bool:
    """Return whether ``method`` takes one protobuf message and returns one."""
    types = [parameter.type for parameter in method.request]
    return len(types) == 1 and all(isinstance(t, type) and issubclass(t, Message) for t in (*types, method.response))


def method_codecs(
    codec: Callable[[Sequence[Any]], Codec[tuple[Any, ...]]], method: Method
) -> tuple[Codec[tuple[Any, ...]], Codec[tuple[Any, ...]]]:
    """Return the codecs ``codec`` makes of the requests and of the responses of ``method``.

    Raises:
        TypeError: ``codec`` cannot carry the request or response of ``method``.
    """
    try:
        request = codec(tuple(parameter.type for parameter in method.request))
    except TypeError as error:
        raise TypeError(f"the request of {method.name}: {error}") from None

    try:
        response = codec((method.response,))
    except TypeError as error:
        raise TypeError(f"the response of {method.name}: {error}") from None

    return request, response
