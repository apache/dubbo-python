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

from dubbo.config import ApplicationConfig
from dubbo.config.fields import to_url_parameters
from dubbo.registry.registration import published_parameters, registers, simplified
from dubbo.url import URL


@pytest.mark.parametrize("check", [registers, simplified])
def test_a_registry_setting_that_is_not_a_boolean_is_rejected(check):
    with pytest.raises(ValueError, match="maybe"):
        check(URL.parse("zookeeper://zk?register=maybe&simplified=maybe"))


def test_the_description_of_the_application_is_published_with_its_services():
    application = ApplicationConfig(
        name="orders", owner="alice,bob", organization="shop", architecture="trade", environment="test"
    )

    assert published_parameters(to_url_parameters(application)) == {
        "application": "orders",
        "owner": "alice,bob",
        "organization": "shop",
        "architecture": "trade",
        "environment": "test",
    }


def test_the_serialization_of_a_service_is_published_for_its_consumers():
    assert published_parameters({"serialization": "hessian2", "threads": "200"}) == {"serialization": "hessian2"}
