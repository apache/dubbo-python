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
from dubbo.common import extension

extension_manager = extension.get_extension_manager()


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

    def do_init(self):
        # init logger
        logger.set_logger_by_name(self.logger_name)

    @property
    def logger_name(self):
        return self._logger_name

    @logger_name.setter
    def logger_name(self, logger_name: str):
        self._logger_name = logger_name
        logger.set_logger_by_name(logger_name)

    def __repr__(self):
        return (f"<ApplicationConfig name={self._name}, "
                f"version={self._version}, "
                f"owner={self._owner}, "
                f"organization={self._organization}, "
                f"architecture={self._architecture}, "
                f"environment={self._environment}>")
