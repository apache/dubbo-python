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

from dubbo.config.application_config import ApplicationConfig


class ConfigManager:
    """
    Configuration manager.
    """
    # unique config in application
    unique_config_types = [
        ApplicationConfig,
    ]

    def __init__(self):
        self._configs_cache = {}

    def add_config(self, config):
        """
        Add configuration.
        :param config: configuration.
        """
        if type(config) not in self.unique_config_types or config.__class__ not in self._configs_cache:
            self._configs_cache[type(config)] = config
        else:
            raise ValueError(f"Config type {type(config)} already exists.")
