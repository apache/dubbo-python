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

from dubbo.utils.converters import comma_separated, milliseconds, to_milliseconds


@pytest.mark.parametrize(("text", "seconds"), [("1500", 1.5), ("0", 0.0)], ids=["fractional-seconds", "zero"])
def test_milliseconds_converts_whole_milliseconds_to_seconds(text, seconds):
    assert milliseconds(text) == seconds


@pytest.mark.parametrize("text", ["-1", "1.5", "fast"], ids=["negative", "fractional-milliseconds", "non-number"])
def test_milliseconds_rejects_what_is_not_whole_milliseconds(text):
    with pytest.raises(ValueError, match=f"must be whole milliseconds, not {text!r}"):
        milliseconds(text)


@pytest.mark.parametrize(("text", "items"), [("a:1, b:2,", ("a:1", "b:2")), (" , ", ())], ids=["trimmed", "empty"])
def test_comma_separated_drops_spaces_and_empty_items(text, items):
    assert comma_separated(text) == items


@pytest.mark.parametrize(
    ("seconds", "text"), [(3, "3000"), (0.0001, "1"), (1.0005, "1001")], ids=["whole", "sub-millisecond", "round-up"]
)
def test_to_milliseconds_rounds_up(seconds, text):
    assert to_milliseconds(seconds) == text
