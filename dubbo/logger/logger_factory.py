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
from typing import Dict

from dubbo.common.constants import LoggerConstants, LoggerLevel
from dubbo.common.url import URL
from dubbo.logger import Logger, LoggerAdapter
from dubbo.logger.internal.logger_adapter import InternalLoggerAdapter

_default_config = URL(
    protocol=LoggerConstants.LOGGER_DRIVER_VALUE,
    host=LoggerConstants.LOGGER_LEVEL_VALUE.value,
    port=None,
    parameters={
        LoggerConstants.LOGGER_DRIVER_KEY: LoggerConstants.LOGGER_DRIVER_VALUE,
        LoggerConstants.LOGGER_LEVEL_KEY: LoggerConstants.LOGGER_LEVEL_VALUE.value,
        LoggerConstants.LOGGER_CONSOLE_ENABLED_KEY: str(
            LoggerConstants.LOGGER_CONSOLE_ENABLED_VALUE
        ),
        LoggerConstants.LOGGER_FILE_ENABLED_KEY: str(
            LoggerConstants.LOGGER_FILE_ENABLED_VALUE
        ),
    },
)


class LoggerFactory:
    """
    Factory class to create loggers.
    """

    # logger adapter
    _logger_adapter = InternalLoggerAdapter(_default_config)
    # A dictionary to store all the loggers.
    _loggers: Dict[str, Logger] = {}
    # A lock to protect the loggers.
    _loggers_lock = threading.Lock()

    @classmethod
    def set_logger_adapter(cls, logger_adapter) -> None:
        """
        Set logger config
        """
        cls._logger_adapter = logger_adapter
        with cls._loggers_lock:
            # update all loggers
            cls._loggers = {
                name: cls._logger_adapter.get_logger(name) for name in cls._loggers
            }

    @classmethod
    def get_logger_adapter(cls) -> LoggerAdapter:
        """
        Get the logger adapter.

        Returns:
            LoggerAdapter: The current logger adapter.
        """
        return cls._logger_adapter

    @classmethod
    def get_logger(cls, name: str) -> Logger:
        """
        Get the logger by name.

        Args:
            name (str): The name of the logger to retrieve.

        Returns:
            Logger: An instance of the requested logger.
        """
        logger = cls._loggers.get(name)
        if logger is None:
            with cls._loggers_lock:
                if name not in cls._loggers:
                    cls._loggers[name] = cls._logger_adapter.get_logger(name)
                logger = cls._loggers[name]
        return logger

    @classmethod
    def get_level(cls) -> LoggerLevel:
        """
        Get the current logging level.

        Returns:
            LoggerLevel: The current logging level.
        """
        return cls._logger_adapter.level

    @classmethod
    def set_level(cls, level: LoggerLevel) -> None:
        """
        Set the logging level.

        Args:
            level (LoggerLevel): The logging level to set.
        """
        cls._logger_adapter.level = level
