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

import random

import pytest


@pytest.fixture
def invokers(provider):
    def create(*queries: str, port: int = 50051):
        return tuple(
            provider(f"10.0.0.{index}", query=query.removeprefix("?"), port=port)
            for index, query in enumerate(queries, 1)
        )

    return create


@pytest.fixture(autouse=True)
def random_state():
    state = random.getstate()
    random.seed(7)
    yield
    random.setstate(state)
