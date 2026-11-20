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

"""Convert the text values of Dubbo URL parameters and configuration.

Each converter takes the text and raises `ValueError` to reject it, so it
works with `dubbo.URL.get_parameter`.
"""

import math

from attrs.converters import to_bool

__all__ = ["boolean", "comma_separated", "is_true", "milliseconds", "to_milliseconds", "to_text"]


# Converts true, t, yes, y, on and 1, or false, f, no, n, off and 0, in any case.
boolean = to_bool


def is_true(value: object) -> bool:
    """Return whether ``value`` reads ``true`` in any case; anything else, such as a value another side sent, is false."""
    return str(value).lower() == "true"


def to_text(value: object) -> str:
    """Convert a value to its text in a URL parameter or a rule, booleans in lowercase and ``None`` as ``null``, as every Dubbo implementation spells them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return "null" if value is None else str(value)


def milliseconds(value: str) -> float:
    """Convert whole milliseconds, such as ``3000``, to seconds."""
    try:
        count = int(value)
    except ValueError:
        count = -1
    if count < 0:
        raise ValueError(f"must be whole milliseconds, not {value!r}")
    return count / 1000


def to_milliseconds(seconds: float) -> str:
    """Convert seconds to whole milliseconds, rounded up so a positive time never becomes ``0``."""
    return str(math.ceil(seconds * 1000))


def comma_separated(value: str) -> tuple[str, ...]:
    """Convert a comma-separated list, such as ``a, b``, dropping surrounding spaces and empty items."""
    return tuple(item for item in (item.strip() for item in value.split(",")) if item)
