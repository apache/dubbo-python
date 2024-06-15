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

"""
This module provides an extension point for logger adapters.
"""
from typing import Dict

from dubbo.common.url import URL
from dubbo.logger import LoggerAdapter

# A dictionary to store all the logger adapters. key: name, value: logger adapter class
_logger_adapter_dict: Dict[str, type[LoggerAdapter]] = {}


def register_logger_adapter(name: str):
    """
    A decorator to register a logger class to the logger extension point.

    This function returns a decorator that registers the decorated class
    as a logger adapter under the specified name.

    Args:
        name (str): The name to register the logger adapter under.

    Returns:
        Callable[[Type[LoggerAdapter]], Type[LoggerAdapter]]:
        A decorator function that registers the logger class.
    """

    def wrapper(cls):
        _logger_adapter_dict[name] = cls
        return cls

    return wrapper


def get_logger_adapter(name: str, config: URL) -> LoggerAdapter:
    """
    Get a logger adapter instance by name.

    This function retrieves a logger adapter class by its registered name and
    instantiates it with the provided arguments.

    Args:
        name (str): The name of the logger adapter to retrieve.
        config (URL): The config of the logger adapter to retrieve.

    Returns:
        LoggerAdapter: An instance of the requested logger adapter.
    Raises:
        KeyError: If no logger adapter is registered under the provided name.
    """
    logger_adapter = _logger_adapter_dict[name]
    return logger_adapter(config)
