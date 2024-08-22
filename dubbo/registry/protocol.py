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

from dubbo.cluster import Directory
from dubbo.cluster.directories import RegistryDirectory
from dubbo.cluster.failfast_cluster import FailfastCluster
from dubbo.configs import RegistryConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Invoker, Protocol
from dubbo.registry import RegistryFactory
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

    def export(self, url: URL):
        # get the server registry
        registry = self._factory.get_registry(url)

        ref_url = url.attributes[common_constants.EXPORT_KEY]
        registry.register(ref_url)
        # continue the export process
        self._protocol.export(ref_url)

    def refer(self, url: URL) -> Invoker:
        registry = self._factory.get_registry(url)

        # create the directory
        directory: Directory = RegistryDirectory(registry, self._protocol, url)

        # continue the refer process
        return FailfastCluster().join(directory)
