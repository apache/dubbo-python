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
from dubbo import logger
from dubbo.common.extension import ExtensionManager


class ApplicationConfig:
    """
    Application Config
    """

    def __init__(
            self,
            name: str,
            version: str = '',
            owner: str = '',
            organization: str = '',
            architecture: str = '',
            environment: str = '',
            logger_name: str = 'loguru'):
        self._name = name
        self._version = version
        self._owner = owner
        self._organization = organization
        self._architecture = architecture
        self._environment = environment
        self._logger_name = logger_name
        self._extension_manager = ExtensionManager()

        # init application config
        self.do_init()

    def do_init(self):
        # init ExtensionManager
        self._extension_manager.initialize()
        # init logger
        self._update_logger(self._logger_name)

    @property
    def logger_name(self):
        return self._logger_name

    @logger_name.setter
    def logger_name(self, logger_name: str):
        self._logger_name = logger_name
        self._update_logger(logger_name)

    def _update_logger(self, logger_name: str):
        """
        Update global logger instance.
        """
        # get logger instance
        instance = self._extension_manager.get_extension_loader(logger.Logger).get_instance(logger_name)
        # update logger
        logger.set_logger(instance)

    def __repr__(self):
        return (f"<ApplicationConfig name={self._name}, "
                f"version={self._version}, "
                f"owner={self._owner}, "
                f"organization={self._organization}, "
                f"architecture={self._architecture}, "
                f"environment={self._environment}>")
