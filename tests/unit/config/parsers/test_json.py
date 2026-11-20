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

import sys

import pytest

from dubbo.config import ConfigParseError
from dubbo.config.parsers.json import JsonParser


@pytest.mark.parametrize("text", ["[]", "null", "true", "123"])
def test_json_requires_mapping(text):
    with pytest.raises(ConfigParseError, match="mapping"):
        JsonParser().loads(text)


def test_json_error_keeps_original_cause():
    with pytest.raises(ConfigParseError, match="invalid JSON configuration") as caught:
        JsonParser().loads("{broken")
    assert isinstance(caught.value.__cause__, ValueError)


@pytest.fixture
def integer_limit():
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    yield
    sys.set_int_max_str_digits(previous)


def test_json_integer_limit_is_reported_as_a_parse_error(integer_limit):
    text = '{"value": ' + "1" * 641 + "}"

    with pytest.raises(ConfigParseError, match="invalid JSON configuration") as caught:
        JsonParser().loads(text)

    assert isinstance(caught.value.__cause__, ValueError)


def test_json_decoder_depth_limit_is_reported_as_a_parse_error():
    # Deeper than Python 3.14 parses too, which bounds the stack rather than the calls.
    text = '{"value": ' + "[" * 1_000_000 + "0" + "]" * 1_000_000 + "}"
    with pytest.raises(ConfigParseError, match="invalid JSON configuration") as caught:
        JsonParser().loads(text)
    assert isinstance(caught.value.__cause__, RecursionError)
