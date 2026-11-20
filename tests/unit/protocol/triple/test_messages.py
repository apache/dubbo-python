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

import pytest
from google.protobuf.wrappers_pb2 import StringValue

from dubbo import Method, Parameter, RpcType
from dubbo.protocol.triple.messages import method_messages
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.serialization.protobuf import ProtobufSerialization
from dubbo.url import URL


def _method(*parameters: object, response: object = StringValue, rpc_type: RpcType = RpcType.UNARY) -> Method:
    return Method(
        name="Say",
        rpc_type=rpc_type,
        request=tuple(Parameter(name=f"p{i}", type=t) for i, t in enumerate(parameters)),
        response=response,
    )


@pytest.mark.parametrize(
    ("method", "message"),
    [
        (_method(), "the request of Say: protobuf carries one message"),
        (_method(StringValue, StringValue), "the request of Say: protobuf carries one message"),
        (_method(str), "the request of Say: protobuf carries messages"),
        (_method(StringValue, response=None), "the response of Say: protobuf carries messages, not None"),
    ],
)
def test_triple_carries_one_message_each_way(method: Method, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        method_messages(ProtobufSerialization(URL(protocol="tri")), method)


def test_only_a_format_of_java_objects_travels_wrapped_with_its_exceptions(hessian2: Hessian2Serialization) -> None:
    method = Method(
        name="greet", request=(Parameter(name="name", type=str), Parameter(name="times", type=int)), response=str
    )

    say = Method(name="Say", request=(Parameter(name="request", type=StringValue),), response=StringValue)
    plain = method_messages(ProtobufSerialization(URL(protocol="tri")), say)
    wrapped = method_messages(hessian2, method)

    assert (plain.content_subtype, plain.exception) == ("proto", None)
    assert wrapped.content_subtype == "proto"
    assert wrapped.exception is not None
    assert wrapped.request.decode(wrapped.request.encode(("bob", 2))) == ("bob", 2)


def test_protobuf_messages_travel_as_themselves_in_a_format_of_java_objects(hessian2: Hessian2Serialization) -> None:
    say = Method(name="Say", request=(Parameter(name="request", type=StringValue),), response=StringValue)

    messages = method_messages(hessian2, say)

    assert (messages.content_subtype, messages.exception) == ("proto", None)
    assert messages.request.encode((StringValue(value="bob"),)) == StringValue(value="bob").SerializeToString()
