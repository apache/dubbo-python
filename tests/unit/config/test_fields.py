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

import attrs

from dubbo.config.fields import to_url_parameters, url_nested, url_parameter
from dubbo.utils.converters import to_milliseconds


@attrs.define(frozen=True, kw_only=True)
class Layer:
    timeout: float | None = attrs.field(default=None, metadata=url_parameter("timeout", to_milliseconds))
    check: bool | None = attrs.field(default=None, metadata=url_parameter("check"))
    retries: int | None = attrs.field(default=None, metadata=url_parameter("retries", default=2))
    note: str | None = None


def test_declared_fields_layer_from_low_to_high_and_skip_unset_values():
    low = Layer(timeout=1, check=True, note="not a parameter")
    high = Layer(timeout=2.5)

    assert to_url_parameters(low) == {"timeout": "1000", "check": "true", "retries": "2"}
    assert to_url_parameters(low, high) == {"timeout": "2500", "check": "true", "retries": "2"}
    assert to_url_parameters(Layer()) == {"retries": "2"}


def test_default_applies_only_when_no_layer_sets_the_field():
    assert to_url_parameters(Layer(retries=0), Layer())["retries"] == "0"
    assert to_url_parameters(Layer(), Layer(retries=5))["retries"] == "5"


@attrs.define(frozen=True, kw_only=True)
class Outer:
    retries: int | None = attrs.field(default=None, metadata=url_parameter("retries"))
    inner: Layer = attrs.field(factory=Layer, metadata=url_nested())
    methods: dict[str, Layer] = attrs.field(factory=dict, metadata=url_nested())
    parameters: dict[str, str] = attrs.field(factory=dict, metadata=url_nested())


def test_nested_configurations_join_layer_by_layer_and_override_extra_parameters():
    low = Outer(inner=Layer(timeout=1), methods={"get": Layer(check=True)}, parameters={"check": "x", "custom": "a"})
    high = Outer(retries=7, inner=Layer(timeout=2), parameters={"custom": "b"})

    assert to_url_parameters(low, high) == {
        "retries": "7",
        "timeout": "2000",
        "check": "x",
        "custom": "b",
        "get.check": "true",
        "get.retries": "2",
    }
