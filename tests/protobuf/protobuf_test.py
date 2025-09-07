#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import pytest

from dubbo.codec.protobuf_codec import GoogleProtobufMessageHandler, PrimitiveHandler, ProtobufTransportCodec
from dubbo.codec.protobuf_codec.protobuf_codec import DeserializationException, SerializationException


def test_primitive_roundtrip_string():
    codec = ProtobufTransportCodec(parameter_types=[str], return_type=str)

    # Encode
    encoded = codec.encode_parameter("hello world")
    assert isinstance(encoded, bytes)

    # Decode
    decoded = codec.decode_return_value(encoded)
    assert decoded == "hello world"


def test_primitive_roundtrip_int():
    codec = ProtobufTransportCodec(parameter_types=[int], return_type=int)

    encoded = codec.encode_parameter(12345)
    decoded = codec.decode_return_value(encoded)

    assert isinstance(decoded, int)
    assert decoded == 12345


def test_primitive_invalid_type_raises():
    codec = ProtobufTransportCodec(parameter_types=[dict], return_type=dict)

    with pytest.raises(SerializationException):
        codec.encode_parameter({"a": 1})


def test_decode_with_no_return_type_raises():
    codec = ProtobufTransportCodec(parameter_types=[str], return_type=None)

    data = PrimitiveHandler().encode("hello", str)

    with pytest.raises(DeserializationException):
        codec.decode_return_value(data)


@pytest.mark.skipif(not GoogleProtobufMessageHandler.__module__, reason="google.protobuf not available")
def test_google_protobuf_roundtrip():
    from generated.greet_pb2 import GreeterReply, GreeterRequest

    codec = ProtobufTransportCodec(parameter_types=[GreeterRequest], return_type=GreeterReply)

    req = GreeterRequest(name="Alice")
    encoded = codec.encode_parameter(req)

    assert isinstance(encoded, bytes)

    # Fake server response
    reply = GreeterReply(message="Hello Alice")
    reply_bytes = reply.SerializeToString()

    decoded = codec.decode_return_value(reply_bytes)
    assert isinstance(decoded, GreeterReply)
    assert decoded.message == "Hello Alice"
