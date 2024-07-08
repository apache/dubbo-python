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
from typing import Any

from dubbo.constants.logger_constants import Level
from dubbo.url import URL


class Logger:
    """
    Logger Interface, which is used to log messages.
    """

    def log(self, level: Level, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a message at the specified logging level.

        Args:
            level (Level): The logging level.
            msg (str): The log message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("log() is not implemented.")

    def debug(self, msg: str, *args, **kwargs) -> None:
        """
        Log a debug message.

        Args:
            msg (str): The debug message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("debug() is not implemented.")

    def info(self, msg: str, *args, **kwargs) -> None:
        """
        Log an info message.

        Args:
            msg (str): The info message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("info() is not implemented.")

    def warning(self, msg: str, *args, **kwargs) -> None:
        """
        Log a warning message.

        Args:
            msg (str): The warning message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("warning() is not implemented.")

    def error(self, msg: str, *args, **kwargs) -> None:
        """
        Log an error message.

        Args:
            msg (str): The error message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("error() is not implemented.")

    def critical(self, msg: str, *args, **kwargs) -> None:
        """
        Log a critical message.

        Args:
            msg (str): The critical message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("critical() is not implemented.")

    def fatal(self, msg: str, *args, **kwargs) -> None:
        """
        Log a fatal message.

        Args:
            msg (str): The fatal message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("fatal() is not implemented.")

    def exception(self, msg: str, *args, **kwargs) -> None:
        """
        Log an exception message.

        Args:
            msg (str): The exception message.
            *args (Any): Additional positional arguments.
            **kwargs (Any): Additional keyword arguments.
        """
        raise NotImplementedError("exception() is not implemented.")

    def is_enabled_for(self, level: Level) -> bool:
        """
        Is this logger enabled for level 'level'?
        Args:
            level (Level): The logging level.
        Return:
            bool: Whether the logging level is enabled.
        """
        raise ValueError("is_enabled_for() is not implemented.")


class LoggerAdapter:
    """
    Logger Adapter Interface, which is used to support different logging libraries.
    Attributes:
        _config(URL): logger adapter configuration.
    """

    _config: URL

    def __init__(self, config: URL):
        """
        Initialize the logger adapter.

        Args:
            config(URL): config (URL): The config of the logger adapter.
        """
        self._config = config

    def get_logger(self, name: str) -> Logger:
        """
        Get a logger by name.

        Args:
            name (str): The name of the logger.

        Returns:
            Logger: An instance of the logger.
        """
        raise NotImplementedError("get_logger() is not implemented.")

    @property
    def level(self) -> Level:
        """
        Get the current logging level.

        Returns:
            Level: The current logging level.
        """
        raise NotImplementedError("get_level() is not implemented.")

    @level.setter
    def level(self, level: Level) -> None:
        """
        Set the logging level.

        Args:
            level (Level): The logging level to set.
        """
        raise NotImplementedError("set_level() is not implemented.")
