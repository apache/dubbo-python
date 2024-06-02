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
from dubbo.config.application_config import ApplicationConfig
from dubbo.config.config_manger import ConfigManager
from dubbo.config.reference_config import ReferenceConfig


class Dubbo:
    """
    Dubbo program entry.
    """
    _instance = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        Singleton mode.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._config_manager: ConfigManager = ConfigManager()

    def with_application(self, application_config: ApplicationConfig) -> 'Dubbo':
        """
        Set application configuration.
        :return: Dubbo instance.
        """
        self._config_manager.add_config(application_config)
        return self

    def with_reference(self, reference_config: ReferenceConfig) -> 'Dubbo':
        """
        Set reference configuration.
        """
        self._config_manager.add_config(reference_config)
        return self

    def start(self):
        """
        Start Dubbo.
        """
        pass
