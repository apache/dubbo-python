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

import typing

from dubbo.config.data import ConfigData
from dubbo.config.exceptions import ConfigReadError
from dubbo.extension import ExtensionError, extension_point, extensions

__all__ = ["ConfigParser", "get_parser"]


@extension_point("apache_dubbo.config.parser")
class ConfigParser(typing.Protocol):
    """Reads one configuration format, such as YAML, into nested data.

    Implementations take no arguments to create.
    """

    def loads(self, text: str, /) -> ConfigData:
        """Return the data ``text`` holds.

        The result is a mapping with string keys whose sections are nested
        mappings, in the shape of DubboConfig: ``{"application": {"name":
        "orders"}}``. Scalars keep the format's native types or stay strings
        to be converted later. Callers treat the result as read-only.

        Raises:
            ConfigParseError: Invalid syntax or a root that is not a mapping.
        """
        ...


def get_parser(name: str) -> ConfigParser:
    """Return the parser of the format ``name``, such as ``yaml`` or ``json``, in any case.

    Raises:
        ConfigReadError: No parser by that name loads.
    """
    try:
        return extensions.get(ConfigParser, name.lower())()
    except ExtensionError as error:
        raise ConfigReadError(f"cannot load configuration parser {name!r}") from error
