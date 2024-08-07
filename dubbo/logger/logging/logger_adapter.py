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

import logging
import os
import sys
from functools import cache
from logging import handlers

from dubbo.common import constants as common_constants
from dubbo.common.url import URL
from dubbo.logger import Logger, LoggerAdapter
from dubbo.logger import constants as logger_constants
from dubbo.logger.constants import LEVEL_KEY, Level
from dubbo.logger.logging import formatter
from dubbo.logger.logging.logger import LoggingLogger

"""This module provides the logging logger implementation. -> logging module"""

__all__ = ["LoggingLoggerAdapter"]


class LoggingLoggerAdapter(LoggerAdapter):
    """
    Internal logger adapter responsible for creating loggers and encapsulating the logging.getLogger() method.
    """

    __slots__ = ["_level"]

    def __init__(self, config: URL):
        """
        Initialize the LoggingLoggerAdapter with the given configuration.

        :param config: The configuration URL for the logger adapter.
        :type config: URL
        """
        super().__init__(config)
        # Set level
        level_name = config.parameters.get(LEVEL_KEY)
        self._level = Level.get_level(level_name) if level_name else Level.DEBUG
        self._update_level()

    def get_logger(self, name: str) -> Logger:
        """
        Create a logger instance by name.

        :param name: The logger name.
        :type name: str
        :return: An instance of the logger.
        :rtype: Logger
        """
        logger_instance = logging.getLogger(name)
        # clean up handlers
        logger_instance.handlers.clear()

        # Add console handler
        console_enabled = self._config.parameters.get(
            logger_constants.CONSOLE_ENABLED_KEY,
            str(logger_constants.DEFAULT_CONSOLE_ENABLED_VALUE),
        )
        if console_enabled.lower() == common_constants.TRUE_VALUE or bool(
            sys.stdout and sys.stdout.isatty()
        ):
            logger_instance.addHandler(self._get_console_handler())

        # Add file handler
        file_enabled = self._config.parameters.get(
            logger_constants.FILE_ENABLED_KEY,
            str(logger_constants.DEFAULT_FILE_ENABLED_VALUE),
        )
        if file_enabled.lower() == common_constants.TRUE_VALUE:
            logger_instance.addHandler(self._get_file_handler())

        if not logger_instance.handlers:
            # It's intended to be used to avoid the "No handlers could be found for logger XXX" one-off warning.
            logger_instance.addHandler(logging.NullHandler())

        return LoggingLogger(logger_instance)

    @cache
    def _get_console_handler(self) -> logging.StreamHandler:
        """
        Get the console handler, avoiding duplicate creation with caching.

        :return: The console handler.
        :rtype: logging.StreamHandler
        """
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter.ColorFormatter())

        return console_handler

    @cache
    def _get_file_handler(self) -> logging.Handler:
        """
        Get the file handler, avoiding duplicate creation with caching.

        :return: The file handler.
        :rtype: logging.Handler
        """
        # Get file path
        file_dir = self._config.parameters.get(logger_constants.FILE_DIR_KEY)
        file_name = self._config.parameters.get(
            logger_constants.FILE_NAME_KEY, logger_constants.DEFAULT_FILE_NAME_VALUE
        )
        file_path = os.path.join(file_dir, file_name)
        # Get backup count
        backup_count = int(
            self._config.parameters.get(
                logger_constants.FILE_BACKUP_COUNT_KEY,
                logger_constants.DEFAULT_FILE_BACKUP_COUNT_VALUE,
            )
        )
        # Get rotate type
        rotate_type = self._config.parameters.get(logger_constants.FILE_ROTATE_KEY)

        # Set file Handler
        file_handler: logging.Handler
        if rotate_type == logger_constants.FileRotateType.SIZE.value:
            # Set RotatingFileHandler
            max_bytes = int(
                self._config.parameters.get(logger_constants.FILE_MAX_BYTES_KEY)
            )
            file_handler = handlers.RotatingFileHandler(
                file_path, maxBytes=max_bytes, backupCount=backup_count
            )
        elif rotate_type == logger_constants.FileRotateType.TIME.value:
            # Set TimedRotatingFileHandler
            interval = int(
                self._config.parameters.get(logger_constants.FILE_INTERVAL_KEY)
            )
            file_handler = handlers.TimedRotatingFileHandler(
                file_path, interval=interval, backupCount=backup_count
            )
        else:
            # Set FileHandler
            file_handler = logging.FileHandler(file_path)

        # Add file_handler
        file_handler.setFormatter(formatter.NoColorFormatter())
        return file_handler

    @property
    def level(self) -> Level:
        """
        Get the logging level.

        :return: The current logging level.
        :rtype: Level
        """
        return self._level

    @level.setter
    def level(self, level: Level) -> None:
        """
        Set the logging level.

        :param level: The logging level to set.
        :type level: Level
        """
        if level == self._level or level is None:
            return
        self._level = level
        self._update_level()

    def _update_level(self):
        """
        Update the log level by modifying the root logger.
        """
        # Get the root logger
        root_logger = logging.getLogger()
        # Set the logging level
        root_logger.setLevel(self._level.value)
