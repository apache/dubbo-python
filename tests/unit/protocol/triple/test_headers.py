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

from dubbo.protocol.triple.headers import percent_decode, percent_encode


def test_grpc_message_percent_encodes_all_but_printable_ascii() -> None:
    assert percent_encode("a b%c\n失") == b"a b%25c%0A%E5%A4%B1"
    assert percent_decode(b"a b%25c%0A%E5%A4%B1") == "a b%c\n失"


def test_grpc_message_keeps_malformed_escapes() -> None:
    assert percent_decode(b"100%zz") == "100%zz"
    assert percent_decode(b"%E5") == "�"
