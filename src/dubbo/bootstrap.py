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

from dubbo.classes import SingletonBase
from dubbo.configs import (
    ApplicationConfig,
    LoggerConfig,
    ReferenceConfig,
    RegistryConfig,
)
from dubbo.constants import common_constants
from dubbo.loggers import loggerFactory

_LOGGER = loggerFactory.get_logger()


class Dubbo(SingletonBase):
    """
    Dubbo class. This class is used to initialize the Dubbo framework.
    """

    def __init__(
        self,
        application_config: Optional[ApplicationConfig] = None,
        registry_config: Optional[RegistryConfig] = None,
        logger_config: Optional[LoggerConfig] = None,
    ):
        """
        Initialize a new Dubbo bootstrap.
        :param application_config: The application configuration.
        :type application_config: Optional[ApplicationConfig]
        :param registry_config: The registry configuration.
        :type registry_config: Optional[RegistryConfig]
        :param logger_config: The logger configuration.
        :type logger_config: Optional[LoggerConfig]
        """
        self._initialized = False
        self._global_lock = threading.Lock()

        self._application_config = application_config
        self._registry_config = registry_config
        self._logger_config = logger_config

        # check and set the default configuration
        self._check_default()

        # initialize the Dubbo framework
        self._initialize()

    @property
    def application_config(self) -> Optional[ApplicationConfig]:
        """
        Get the application configuration.
        :return: The application configuration.
        :rtype: Optional[ApplicationConfig]
        """
        return self._application_config

    @property
    def registry_config(self) -> Optional[RegistryConfig]:
        """
        Get the registry configuration.
        :return: The registry configuration.
        :rtype: Optional[RegistryConfig]
        """
        return self._registry_config

    @property
    def logger_config(self) -> Optional[LoggerConfig]:
        """
        Get the logger configuration.
        :return: The logger configuration.
        :rtype: Optional[LoggerConfig]
        """
        return self._logger_config

    def _check_default(self):
        """
        Check and set the default configuration.
        """
        # set default application configuration
        if not self._application_config:
            self._application_config = ApplicationConfig(common_constants.DUBBO_VALUE)

        if self._registry_config:
            if not self._registry_config.version and self.application_config.version:
                self._registry_config.version = self.application_config.version

    def _initialize(self):
        """
        Initialize the Dubbo framework.
        """
        with self._global_lock:
            if self._initialized:
                return

            # set logger configuration
            if self._logger_config:
                loggerFactory.set_config(self._logger_config)

            self._initialized = True

    def create_client(self, reference_config: ReferenceConfig):
        """
        Create a new Dubbo client.
        :param reference_config: The reference configuration.
        :type reference_config: ReferenceConfig
        """
        try:
            from dubbo import Client
            return Client(reference_config, self)
        except Exception as e:
            _LOGGER.error(f"Failed to create client: {e}")
            raise

    def create_server(self, config):
        """
        Create a new Dubbo server.
        :param config: The service configuration.
        :type config: ServiceConfig
        """
        try:
            from dubbo import Server
            return Server(config, self)
        except Exception as e:
            _LOGGER.error(f"Failed to create server: {e}")
            raise
