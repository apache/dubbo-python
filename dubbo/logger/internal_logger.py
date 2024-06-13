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
from typing import Dict

from dubbo.common import extension
from dubbo.logger import Level, Logger, LoggerAdapter

"""This module provides the internal logger implementation. -> logging module"""

# The mapping from the logging level to the internal logging level.
_level_map: Dict[Level, int] = {
    Level.DEBUG: logging.DEBUG,
    Level.INFO: logging.INFO,
    Level.WARNING: logging.WARNING,
    Level.ERROR: logging.ERROR,
    Level.CRITICAL: logging.CRITICAL,
    Level.FATAL: logging.FATAL,
}


class InternalLogger(Logger):
    """
    The internal logger implementation.
    """

    def __init__(self, internal_logger: logging.Logger):
        self._logger = internal_logger

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        # Add the stacklevel to the keyword arguments.
        kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 2
        self._logger.log(level, msg, *args, **kwargs)

    def log(self, level: Level, msg: str, *args, **kwargs) -> None:
        self._log(_level_map[level], msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.FATAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        if kwargs.get("exc_info") is None:
            kwargs["exc_info"] = True
        self.error(msg, *args, **kwargs)


@extension.register_logger_adapter("internal")
class InternalLoggerAdapter(LoggerAdapter):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the default logging level to DEBUG.
        self._level = Level.DEBUG
        self._update_level(Level.DEBUG)

    def get_logger(self, name: str) -> Logger:
        """
        Create a logger instance by name.
        Args:
            name (str): The logger name.
        Returns:
            Logger: The InternalLogger instance.
        """
        # TODO enable config by args
        logger_instance = logging.getLogger(name)
        # Create a formatter
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(module)s:%(funcName)s:%(lineno)d - [Dubbo] %(message)s"
        )
        # Add a console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger_instance.addHandler(console_handler)
        return InternalLogger(logger_instance)

    @property
    def level(self) -> Level:
        """
        Get the logging level.
        Returns:
            Level: The logging level.
        """
        return self._level

    @level.setter
    def level(self, level: Level) -> None:
        """
        Set the logging level.
        Args:
            level (Level): The logging level.
        """
        if level == self._level or level is None:
            return
        self._level = level
        self._update_level(level)

    def _update_level(self, level: Level) -> None:
        """
        Update the logging level.
        """
        # Get the root logger
        root_logger = logging.getLogger()
        # Set the logging level
        root_logger.setLevel(level.name)
