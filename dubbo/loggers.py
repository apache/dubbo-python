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
import enum
import logging
import re
import threading
from typing import Optional

from dubbo.configs import LoggerConfig

__all__ = ["loggerFactory"]


class ColorFormatter(logging.Formatter):
    """
    A formatter with color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    @enum.unique
    class Colors(enum.Enum):
        """
        Colors for log messages.
        """

        END = "\033[0m"
        BOLD = "\033[1m"
        BLUE = "\033[34m"
        GREEN = "\033[32m"
        PURPLE = "\033[35m"
        CYAN = "\033[36m"
        RED = "\033[31m"
        YELLOW = "\033[33m"
        GREY = "\033[38;5;240m"

    COLOR_LEVEL_MAP = {
        "DEBUG": Colors.BLUE.value,
        "INFO": Colors.GREEN.value,
        "WARNING": Colors.YELLOW.value,
        "ERROR": Colors.RED.value,
        "CRITICAL": Colors.RED.value + Colors.BOLD.value,
    }

    DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    LOG_FORMAT: str = (
        f"{Colors.GREEN.value}%(asctime)s{Colors.END.value}"
        " | "
        f"%(level_color)s%(levelname)s{Colors.END.value}"
        " | "
        f"{Colors.CYAN.value}%(module)s:%(funcName)s:%(lineno)d{Colors.END.value}"
        " - "
        f"{Colors.PURPLE.value}[Dubbo]{Colors.END.value} "
        f"%(msg_color)s%(message)s{Colors.END.value}"
    )

    def __init__(self):
        super().__init__(self.LOG_FORMAT, self.DATE_FORMAT)

    def format(self, record) -> str:
        levelname = record.levelname
        record.level_color = record.msg_color = self.COLOR_LEVEL_MAP.get(levelname)
        return super().format(record)


class NoColorFormatter(logging.Formatter):
    """
    A formatter without color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    def __init__(self):
        color_re = re.compile(r"\033\[[0-9;]*\w|%\((msg_color|level_color)\)s")
        self.log_format = color_re.sub("", ColorFormatter.LOG_FORMAT)
        super().__init__(self.log_format, ColorFormatter.DATE_FORMAT)


class _LoggerFactory:
    """
    The logger factory.
    """

    _logger_lock = threading.RLock()
    _config: LoggerConfig = LoggerConfig()
    _logger: Optional[logging.Logger] = None

    @classmethod
    def set_config(cls, config):
        if not isinstance(config, LoggerConfig):
            raise TypeError("config must be an instance of LoggerConfig")

        cls._config = config
        cls._refresh_config()

    @classmethod
    def _refresh_config(cls) -> None:
        """
        Refresh the logger configuration.

        """
        with cls._logger_lock:
            # create logger if not exists
            if not cls._logger:
                cls._logger = logging.getLogger("dubbo")

            # clean up handlers
            cls._logger.handlers.clear()

            config = cls._config

            # set logger level
            cls._logger.setLevel(config.level)

            # add console handler if enabled
            if config.is_console_enabled():
                cls._logger.addHandler(cls._get_console_handler())

            # add file handler if enabled
            if config.is_file_enabled():
                cls._logger.addHandler(cls._get_file_handler())

    @classmethod
    def _get_console_handler(cls) -> logging.StreamHandler:
        """
        Get the console handler

        :return: The console handler.
        :rtype: logging.StreamHandler
        """
        console_handler = logging.StreamHandler()
        if not cls._config.console_config.formatter or cls._config.global_formatter:
            # set default color formatter
            console_handler.setFormatter(ColorFormatter())
        else:
            console_handler.setFormatter(
                logging.Formatter(
                    cls._config.console_config.formatter or cls._config.global_formatter
                )
            )

        return console_handler

    @classmethod
    def _get_file_handler(cls):
        """
        Get the file handler

        :return: The file handler.
        :rtype: logging.FileHandler
        """
        file_handler = logging.FileHandler(
            filename=cls._config.file_config.file_name,
            mode="a",
            encoding="utf-8",
        )
        if not cls._config.file_config.file_formatter or cls._config.global_formatter:
            # set default no color formatter
            file_handler.setFormatter(NoColorFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    cls._config.file_config.file_formatter
                    or cls._config.global_formatter
                )
            )

        return file_handler

    @classmethod
    def get_logger(cls) -> logging.Logger:
        """
        Get the logger. class method.

        :return: The logger.
        :rtype: logging.Logger
        """

        # if logger is not initialized, refresh the config
        if not cls._logger:
            with cls._logger_lock:
                # double check
                if not cls._logger:
                    cls._refresh_config()

        return cls._logger


# expose loggerFactory
loggerFactory = _LoggerFactory
