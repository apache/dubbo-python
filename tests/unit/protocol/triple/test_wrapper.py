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

from typing import Any

import pytest

from dubbo._proto.org.apache.dubbo.triple.triple_wrapper_pb2 import TripleRequestWrapper, TripleResponseWrapper
from dubbo.protocol.triple.wrapper import wrapped_codec
from dubbo.serialization.hessian2 import Hessian2Serialization

pytestmark = pytest.mark.anyio


def test_each_value_travels_alone_beside_its_java_type(hessian2: Hessian2Serialization) -> None:
    codec = wrapped_codec(hessian2, (str, int | None, tuple[str, ...]))

    data = codec.encode(("bob", 7, ("a",)))

    wrapper = TripleRequestWrapper.FromString(data)
    assert wrapper.serializeType == "hessian2"
    assert list(wrapper.argTypes) == ["java.lang.String", "java.lang.Integer", "[Ljava.lang.String;"]
    assert [hessian2.codec((Any,)).decode(argument)[0] for argument in wrapper.args] == ["bob", 7, ["a"]]
    assert codec.decode(data) == ("bob", 7, ("a",))


def test_one_value_is_a_response_wrapper(hessian2: Hessian2Serialization) -> None:
    codec = wrapped_codec(hessian2, (str,))
    value = hessian2.codec((str,)).encode(("bob",))

    assert (
        codec.encode(("bob",))
        == TripleResponseWrapper(serializeType="hessian2", data=value, type="java.lang.String").SerializeToString()
    )


def test_a_wrapper_that_names_hessian4_is_read_as_hessian2(hessian2: Hessian2Serialization) -> None:
    codec = wrapped_codec(hessian2, (str,))
    value = hessian2.codec((str,)).encode(("bob",))

    assert codec.decode(TripleResponseWrapper(serializeType="hessian4", data=value).SerializeToString()) == ("bob",)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\xff", "not a wrapped message"),
        (TripleRequestWrapper(serializeType="fastjson2", args=[b"N"]).SerializeToString(), "in 'fastjson2'"),
        (TripleRequestWrapper(serializeType="hessian2", args=[b"N", b"N"]).SerializeToString(), "expected 1 values"),
    ],
)
def test_a_wrapper_must_hold_one_value_of_each_type_in_the_format(
    hessian2: Hessian2Serialization, data: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        wrapped_codec(hessian2, (Any,)).decode(data)
