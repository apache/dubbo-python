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
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from dubbo.codec.json_codec import JsonTransportCodec


# Optional dataclass and enum examples
@dataclass
class SampleDataClass:
    field1: int
    field2: str


class Color(Enum):
    RED = "red"
    GREEN = "green"


# List of test cases: (input_value, expected_type_after_decoding)
test_cases = [
    ("simple string", str),
    (12345, int),
    (12.34, float),
    (True, bool),
    (datetime(2025, 8, 27, 13, 0, tzinfo=timezone.utc), datetime),
    (Decimal("123.45"), Decimal),
    (set([1, 2, 3]), set),
    (frozenset(["a", "b"]), frozenset),
    (UUID("12345678-1234-5678-1234-567812345678"), UUID),
    (Color.RED, Color),
    (SampleDataClass(field1=1, field2="abc"), SampleDataClass),
]


@pytest.mark.parametrize("value,expected_type", test_cases)
def test_json_codec_roundtrip(value, expected_type):
    codec = JsonTransportCodec(parameter_types=[type(value)], return_type=expected_type)

    # Encode
    encoded = codec.encode_parameters(value)
    assert isinstance(encoded, bytes)

    # Decode
    decoded = codec.decode_return_value(encoded)

    # For dataclass, compare asdict
    if hasattr(value, "__dataclass_fields__"):
        assert asdict(decoded) == asdict(value)
    # For sets/frozensets, compare as sets
    elif isinstance(value, (set, frozenset)):
        assert decoded == value
    # For enum
    elif isinstance(value, Enum):
        assert decoded.value == value.value
    else:
        assert decoded == value
