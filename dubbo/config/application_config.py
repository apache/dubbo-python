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


class ApplicationConfig:
    """
    Application configuration.
    Attributes:
        _name(str): Application name
        _version(str): Application version
        _owner(str): Application owner
        _organization(str): Application organization (BU)
        _environment(str): Application environment, e.g. dev, test or production
    """

    _name: str
    _version: str
    _owner: str
    _organization: str
    _environment: str

    def clone(self) -> "ApplicationConfig":
        """
        Clone the current configuration.
        Returns:
            ApplicationConfig: A new instance of ApplicationConfig.
        """
        return ApplicationConfig()

    @classmethod
    def default_config(cls):
        return cls()
