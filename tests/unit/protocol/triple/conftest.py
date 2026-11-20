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

from dubbo.extension import extensions
from dubbo.serialization.hessian2 import Hessian2Serialization
from dubbo.transport.h2 import H2Client
from dubbo.url import URL


@pytest.fixture
def clients(isolated_extensions):
    clients = []

    class Client:
        def __init__(self, url):
            self.url = url
            self.closed = False
            clients.append(self)

        @property
        def available(self):
            return not self.closed

        async def __aenter__(self):
            return self

        async def aclose(self):
            self.closed = True

    extensions.register(H2Client, "memory", Client)
    return clients


@pytest.fixture
def hessian2() -> Hessian2Serialization:
    return Hessian2Serialization(URL(protocol="tri"))


@pytest.fixture
def client_url():
    return URL(protocol="tri", host="127.0.0.1", port=1, parameters={"triple.client": "memory"})
