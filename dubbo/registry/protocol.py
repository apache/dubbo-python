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
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Optional

from dubbo.configs import RegistryConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Invoker, Protocol
from dubbo.registry import Registry, RegistryFactory
from dubbo.url import URL

__all__ = ["RegistryProtocol"]


class RegistryProtocol(Protocol):
    """
    Registry protocol.
    """

    def __init__(self, config: RegistryConfig, protocol: Protocol):
        self._config = config
        self._protocol = protocol

        self._factory: RegistryFactory = extensionLoader.get_extension(
            RegistryFactory, self._config.protocol
        )()
        self._server_registry: Optional[Registry] = None

    def export(self, url: URL):
        # get the server registry
        self._server_registry = self._factory.get_registry(url)
        self._server_registry.register(url.attributes[common_constants.EXPORT_KEY])
        # continue the export process
        self._protocol.export(url)

    def refer(self, url: URL) -> Invoker:
        pass
