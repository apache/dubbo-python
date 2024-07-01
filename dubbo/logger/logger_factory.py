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

from dubbo.common.constants import logger_constants as logger_constants
from dubbo.common.constants.logger_constants import Level
from dubbo.common.url import URL
from dubbo.logger.logger import Logger, LoggerAdapter
from dubbo.logger.logging.logger_adapter import LoggingLoggerAdapter

# Default logger config with default values.
_default_config = URL(
    protocol=logger_constants.DEFAULT_DRIVER_VALUE,
    host=logger_constants.DEFAULT_LEVEL_VALUE.value,
    parameters={
        logger_constants.DRIVER_KEY: logger_constants.DEFAULT_DRIVER_VALUE,
        logger_constants.LEVEL_KEY: logger_constants.DEFAULT_LEVEL_VALUE.value,
        logger_constants.CONSOLE_ENABLED_KEY: str(
            logger_constants.DEFAULT_CONSOLE_ENABLED_VALUE
        ),
        logger_constants.FILE_ENABLED_KEY: str(
            logger_constants.DEFAULT_FILE_ENABLED_VALUE
        ),
    },
)


class _LoggerFactory:
    """
    LoggerFactory
    Attributes:
        _logger_adapter (LoggerAdapter): The logger adapter.
        _loggers (Dict[str, Logger]): The logger cache.
        _loggers_lock (threading.Lock): The logger lock to protect the logger cache.
    """

    _logger_adapter = LoggingLoggerAdapter(_default_config)
    _loggers: Dict[str, Logger] = {}
    _loggers_lock = threading.Lock()

    @classmethod
    def set_logger_adapter(cls, logger_adapter) -> None:
        """
        Set logger config
        """
        cls._logger_adapter = logger_adapter
        cls._loggers_lock.acquire()
        try:
            # update all loggers
            cls._loggers = {
                name: cls._logger_adapter.get_logger(name) for name in cls._loggers
            }
        finally:
            cls._loggers_lock.release()

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
        if not logger:
            cls._loggers_lock.acquire()
            try:
                if name not in cls._loggers:
                    cls._loggers[name] = cls._logger_adapter.get_logger(name)
                logger = cls._loggers[name]
            finally:
                cls._loggers_lock.release()
        return logger

    @classmethod
    def get_level(cls) -> Level:
        """
        Get the current logging level.

        Returns:
            Level: The current logging level.
        """
        return cls._logger_adapter.level

    @classmethod
    def set_level(cls, level: Level) -> None:
        """
        Set the logging level.

        Args:
            level (Level): The logging level to set.
        """
        cls._logger_adapter.level = level


loggerFactory = _LoggerFactory
