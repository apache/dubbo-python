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

"""A configuration parser for TOML files, with tomllib from the standard library."""

import tomllib

from dubbo.config import ConfigData, ConfigParseError, ConfigParser


class TomlParser(ConfigParser):
    """Reads a TOML document; its tables are the sections of the configuration."""

    def loads(self, text: str, /) -> ConfigData:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ConfigParseError("invalid TOML configuration") from error
