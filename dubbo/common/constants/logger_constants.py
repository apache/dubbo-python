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
import os
from functools import cache


@enum.unique
class LoggerLevel(enum.Enum):
    """
    The logging level enum.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"

    @classmethod
    @cache
    def get_level(cls, level_value: str) -> "LoggerLevel":
        level_value = level_value.upper()
        for level in cls:
            if level_value == level.value:
                return level
        raise ValueError("Log level invalid")


@enum.unique
class LoggerFileRotateType(enum.Enum):
    """
    The file rotating type enum.
    """

    # No rotating.
    NONE = "NONE"
    # Rotate the file by size.
    SIZE = "SIZE"
    # Rotate the file by time.
    TIME = "TIME"


class LoggerConstants:
    """logger configuration constants."""

    """logger config keys"""
    # global config
    LOGGER_LEVEL_KEY = "logger.level"
    LOGGER_DRIVER_KEY = "logger.driver"
    LOGGER_FORMAT_KEY = "logger.format"

    # console config
    LOGGER_CONSOLE_ENABLED_KEY = "logger.console.enable"
    LOGGER_CONSOLE_FORMAT_KEY = "logger.console.format"

    # file logger
    LOGGER_FILE_ENABLED_KEY = "logger.file.enable"
    LOGGER_FILE_FORMAT_KEY = "logger.file.format"
    LOGGER_FILE_DIR_KEY = "logger.file.dir"
    LOGGER_FILE_NAME_KEY = "logger.file.name"
    LOGGER_FILE_ROTATE_KEY = "logger.file.rotate"
    LOGGER_FILE_MAX_BYTES_KEY = "logger.file.maxbytes"
    LOGGER_FILE_INTERVAL_KEY = "logger.file.interval"
    LOGGER_FILE_BACKUP_COUNT_KEY = "logger.file.backupcount"

    """some logger default value"""
    LOGGER_DRIVER_VALUE = "internal"
    LOGGER_LEVEL_VALUE = LoggerLevel.DEBUG
    # console
    LOGGER_CONSOLE_ENABLED_VALUE = True
    # file
    LOGGER_FILE_ENABLED_VALUE = False
    LOGGER_FILE_DIR_VALUE = os.path.expanduser("~")
    LOGGER_FILE_NAME_VALUE = "dubbo.log"
    LOGGER_FILE_MAX_BYTES_VALUE = 10 * 1024 * 1024
    LOGGER_FILE_INTERVAL_VALUE = 1
    LOGGER_FILE_BACKUP_COUNT_VALUE = 10
