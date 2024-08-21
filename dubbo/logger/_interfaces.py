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

import abc
from typing import Any

from dubbo.common.url import URL

from .constants import Level

_all__ = ["Logger", "LoggerAdapter"]


class Logger(abc.ABC):
    """
    Logger Interface, which is used to log messages.
    """

    @abc.abstractmethod
    def log(self, level: Level, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a message at the specified logging level.

        :param level: The logging level.
        :type level: Level
        :param msg: The log message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def debug(self, msg: str, *args, **kwargs) -> None:
        """
        Log a debug message.

        :param msg: The debug message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def info(self, msg: str, *args, **kwargs) -> None:
        """
        Log an info message.

        :param msg: The info message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def warning(self, msg: str, *args, **kwargs) -> None:
        """
        Log a warning message.

        :param msg: The warning message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def error(self, msg: str, *args, **kwargs) -> None:
        """
        Log an error message.

        :param msg: The error message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def critical(self, msg: str, *args, **kwargs) -> None:
        """
        Log a critical message.

        :param msg: The critical message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def fatal(self, msg: str, *args, **kwargs) -> None:
        """
        Log a fatal message.

        :param msg: The fatal message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def exception(self, msg: str, *args, **kwargs) -> None:
        """
        Log an exception message.

        :param msg: The exception message.
        :type msg: str
        :param args: Additional positional arguments.
        :type args: Any
        :param kwargs: Additional keyword arguments.
        :type kwargs: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def is_enabled_for(self, level: Level) -> bool:
        """
        Check if this logger is enabled for the specified level.

        :param level: The logging level.
        :type level: Level
        :return: Whether the logging level is enabled.
        :rtype: bool
        """
        raise NotImplementedError()


class LoggerAdapter(abc.ABC):
    """
    Logger Adapter Interface, which is used to support different logging libraries.
    """

    __slots__ = ["_config"]

    def __init__(self, config: URL):
        """
        Initialize the logger adapter.

        :param config: The configuration of the logger adapter.
        :type config: URL
        """
        self._config = config

    def get_logger(self, name: str) -> Logger:
        """
        Get a logger by name.

        :param name: The name of the logger.
        :type name: str
        :return: An instance of the logger.
        :rtype: Logger
        """
        raise NotImplementedError()

    @property
    def level(self) -> Level:
        """
        Get the current logging level.

        :return: The current logging level.
        :rtype: Level
        """
        raise NotImplementedError()

    @level.setter
    def level(self, level: Level) -> None:
        """
        Set the logging level.

        :param level: The logging level to set.
        :type level: Level
        """
        raise NotImplementedError()
