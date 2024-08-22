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
import threading
from typing import Optional

from dubbo.bootstrap import Dubbo
from dubbo.configs import ServiceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Protocol
from dubbo.registry.protocol import RegistryProtocol
from dubbo.url import URL


class Server:
    """
    Dubbo Server
    """

    def __init__(self, service_config: ServiceConfig, dubbo: Optional[Dubbo] = None):
        self._initialized = False
        self._global_lock = threading.RLock()

        self._service = service_config
        self._dubbo = dubbo or Dubbo()

        self._protocol: Optional[Protocol] = None
        self._url: Optional[URL] = None
        self._exported = False

        # initialize the server
        self._initialize()

    def _initialize(self):
        """
        Initialize the server.
        """
        with self._global_lock:
            if self._initialized:
                return

            # get the protocol
            service_protocol = extensionLoader.get_extension(
                Protocol, self._service.protocol
            )()

            registry_config = self._dubbo.registry_config

            self._protocol = (
                RegistryProtocol(registry_config, service_protocol)
                if self._dubbo.registry_config
                else service_protocol
            )

            # build url
            service_url = self._service.to_url()
            if registry_config:
                self._url = registry_config.to_url().copy()
                self._url.attributes[common_constants.EXPORT_KEY] = service_url
                for k, v in service_url.attributes.items():
                    self._url.attributes[k] = v
            else:
                self._url = service_url

    def start(self):
        """
        Start the server.
        """
        with self._global_lock:
            if self._exported:
                return

            self._protocol.export(self._url)

            self._exported = True
