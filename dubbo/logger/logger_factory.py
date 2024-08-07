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
from typing import Dict, Optional

from dubbo.common import SingletonBase
from dubbo.common.url import URL
from dubbo.logger import Logger, LoggerAdapter
from dubbo.logger import constants as logger_constants
from dubbo.logger.constants import Level

__all__ = ["LoggerFactory"]

# Default logger config with default values.
_DEFAULT_CONFIG = URL(
    scheme=logger_constants.DEFAULT_DRIVER_VALUE,
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


class LoggerFactory(SingletonBase):
    """
    Singleton factory class for creating and managing loggers.

    This class ensures a single instance of the logger factory, provides methods to set and get
    logger adapters, and manages logger instances.
    """

    def __init__(self):
        """
        Initialize the logger factory.

        This method sets up the internal lock, logger adapter, and logger cache.
        """
        self._lock = threading.RLock()
        self._logger_adapter: Optional[LoggerAdapter] = None
        self._loggers: Dict[str, Logger] = {}

    def _ensure_logger_adapter(self) -> None:
        """
        Ensure the logger adapter is set.

        If the logger adapter is not set, this method sets it to the default adapter.
        """
        if not self._logger_adapter:
            with self._lock:
                if not self._logger_adapter:
                    # Import here to avoid circular imports
                    from dubbo.logger.logging.logger_adapter import LoggingLoggerAdapter

                    self.set_logger_adapter(LoggingLoggerAdapter(_DEFAULT_CONFIG))

    def set_logger_adapter(self, logger_adapter: LoggerAdapter) -> None:
        """
        Set the logger adapter.

        :param logger_adapter: The new logger adapter to use.
        :type logger_adapter: LoggerAdapter
        """
        with self._lock:
            self._logger_adapter = logger_adapter
            # Update all loggers
            self._loggers = {
                name: self._logger_adapter.get_logger(name) for name in self._loggers
            }

    def get_logger_adapter(self) -> LoggerAdapter:
        """
        Get the current logger adapter.

        :return: The current logger adapter.
        :rtype: LoggerAdapter
        """
        self._ensure_logger_adapter()
        return self._logger_adapter

    def get_logger(self, name: str) -> Logger:
        """
        Get the logger by name.

        :param name: The name of the logger to retrieve.
        :type name: str
        :return: An instance of the requested logger.
        :rtype: Logger
        """
        self._ensure_logger_adapter()
        logger = self._loggers.get(name)
        if not logger:
            with self._lock:
                if name not in self._loggers:
                    self._loggers[name] = self._logger_adapter.get_logger(name)
                logger = self._loggers[name]
        return logger

    def get_level(self) -> Level:
        """
        Get the current logging level.

        :return: The current logging level.
        :rtype: Level
        """
        self._ensure_logger_adapter()
        return self._logger_adapter.level
