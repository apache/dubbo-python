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
from google.protobuf.wrappers_pb2 import Int64Value, StringValue

from dubbo.extension import extensions
from dubbo.serialization import Serialization
from dubbo.serialization.protobuf import ProtobufSerialization
from dubbo.url import URL


def test_protobuf_is_named_protobuf_and_travels_as_proto() -> None:
    assert extensions.get(Serialization, "protobuf") is ProtobufSerialization
    assert ProtobufSerialization.content_subtype == "proto"


def test_protobuf_codec_preserves_the_message_wire_bytes():
    codec = ProtobufSerialization(URL(protocol="tri")).codec((StringValue,))
    message = StringValue(value="hi")

    assert codec.encode((message,)) == b"\x0a\x02hi"
    assert codec.decode(b"\x0a\x02hi") == (message,)


@pytest.mark.parametrize(
    ("types", "message"),
    [
        ((), "one message of a known type"),
        ((StringValue, StringValue), "one message of a known type"),
        ((str,), "carries messages, not <class 'str'>"),
        ((None,), "carries messages, not None"),
    ],
)
def test_protobuf_rejects_what_is_not_one_message_and_names_the_format_for_python_types(
    types: tuple[object, ...], message: str
) -> None:
    with pytest.raises(TypeError, match=message) as caught:
        ProtobufSerialization(URL(protocol="tri")).codec(types)

    assert str(caught.value).endswith(
        "; set the serialization to hessian2, or use the dubbo protocol, to carry Python types and several parameters"
    )


def test_protobuf_checks_the_message_type() -> None:
    codec = ProtobufSerialization(URL(protocol="tri")).codec((StringValue,))

    # SerializeToString itself would encode the wrong message without complaint.
    with pytest.raises(TypeError, match="expected StringValue, not Int64Value"):
        codec.encode((Int64Value(value=1),))
    with pytest.raises(ValueError, match="not a StringValue"):
        codec.decode(b"\xff\xff")
