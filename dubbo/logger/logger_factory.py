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

from dubbo.common.constants import LoggerLevel
from dubbo.logger.logger import Logger, LoggerAdapter


def initialize_check(func):
    """
    Checks if the logger factory instance is initialized.
    """

    def wrapper(self, *args, **kwargs):
        if not self._initialized:
            with self._initialize_lock:
                if not self._initialized:
                    # initialize LoggerFactory
                    from dubbo.config import LoggerConfig

                    config = LoggerConfig()
                    config.init()
                    self._initialized = True
        return func(self, *args, **kwargs)

    return wrapper


class LoggerFactory:
    """
    Factory class to create loggers. (single object)
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._logger_adapter = None
        # A dictionary to store all the loggers.
        self._loggers = {}
        # A lock to protect the loggers.
        self._loggers_lock = threading.Lock()
        # Initialization flag
        self._initialized = False
        self._initialize_lock = threading.Lock()

    @property
    @initialize_check
    def logger_adapter(self) -> LoggerAdapter:
        return self._logger_adapter

    @logger_adapter.setter
    def logger_adapter(self, logger_adapter) -> None:
        """
        Set logger config
        """
        self._logger_adapter = logger_adapter
        with self._loggers_lock:
            # update all loggers
            self._loggers = {
                name: self._logger_adapter.get_logger(name) for name in self._loggers
            }
        self._initialized = True

    @initialize_check
    def get_logger_adapter(self) -> LoggerAdapter:
        """
        Get the logger adapter.

        Returns:
            LoggerAdapter: The current logger adapter.
        """
        return self._logger_adapter

    @initialize_check
    def get_logger(self, name: str) -> Logger:
        """
        Get the logger by name.

        Args:
            name (str): The name of the logger to retrieve.

        Returns:
            Logger: An instance of the requested logger.
        """
        logger = self._loggers.get(name)
        if logger is None:
            with self._loggers_lock:
                if name not in self._loggers:
                    self._loggers[name] = self._logger_adapter.get_logger(name)
                logger = self._loggers[name]
        return logger

    @property
    @initialize_check
    def level(self) -> LoggerLevel:
        """
        Get the current logging level.

        Returns:
            LoggerLevel: The current logging level.
        """
        return self._logger_adapter.level

    @level.setter
    @initialize_check
    def level(self, level: LoggerLevel) -> None:
        """
        Set the logging level.

        Args:
            level (LoggerLevel): The logging level to set.
        """
        self._logger_adapter.level = level
