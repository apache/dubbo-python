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

from dubbo.extension import ExtensionError
from dubbo.serialization import JavaSerialization, get_java_serialization, get_serialization
from dubbo.serialization.protobuf import ProtobufSerialization
from dubbo.url import URL


def test_get_serialization_reads_the_serialization_parameter() -> None:
    assert isinstance(get_serialization(URL(protocol="tri")), ProtobufSerialization)
    assert isinstance(
        get_serialization(URL(protocol="tri", parameters={"serialization": "protobuf"})), ProtobufSerialization
    )
    with pytest.raises(ExtensionError, match="fastjson2"):
        get_serialization(URL(protocol="tri", parameters={"serialization": "fastjson2"}))


def test_protobuf_carries_no_java_objects() -> None:
    url = URL(protocol="dubbo", parameters={"serialization": "protobuf"})

    assert not isinstance(ProtobufSerialization(url), JavaSerialization)
    with pytest.raises(ValueError, match="'protobuf' does not carry Java objects"):
        get_java_serialization(url)
