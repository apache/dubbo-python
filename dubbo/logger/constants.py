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

__all__ = [
    "Level",
    "FileRotateType",
    "LEVEL_KEY",
    "DRIVER_KEY",
    "CONSOLE_ENABLED_KEY",
    "FILE_ENABLED_KEY",
    "FILE_DIR_KEY",
    "FILE_NAME_KEY",
    "FILE_ROTATE_KEY",
    "FILE_MAX_BYTES_KEY",
    "FILE_INTERVAL_KEY",
    "FILE_BACKUP_COUNT_KEY",
    "DEFAULT_DRIVER_VALUE",
    "DEFAULT_LEVEL_VALUE",
    "DEFAULT_CONSOLE_ENABLED_VALUE",
    "DEFAULT_FILE_ENABLED_VALUE",
    "DEFAULT_FILE_DIR_VALUE",
    "DEFAULT_FILE_NAME_VALUE",
    "DEFAULT_FILE_MAX_BYTES_VALUE",
    "DEFAULT_FILE_INTERVAL_VALUE",
    "DEFAULT_FILE_BACKUP_COUNT_VALUE",
]


@enum.unique
class Level(enum.Enum):
    """
    The logging level enum.

    :cvar DEBUG: Debug level.
    :cvar INFO: Info level.
    :cvar WARNING: Warning level.
    :cvar ERROR: Error level.
    :cvar CRITICAL: Critical level.
    :cvar FATAL: Fatal level.
    :cvar UNKNOWN: Unknown level.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def get_level(cls, level_value: str) -> "Level":
        """
        Get the level from the level value.

        :param level_value: The level value.
        :type level_value: str
        :return: The level. If the level value is invalid, return UNKNOWN.
        :rtype: Level
        """
        level_value = level_value.upper()
        for level in cls:
            if level_value == level.value:
                return level
        return cls.UNKNOWN


@enum.unique
class FileRotateType(enum.Enum):
    """
    The file rotating type enum.

    :cvar NONE: No rotating.
    :cvar SIZE: Rotate the file by size.
    :cvar TIME: Rotate the file by time.
    """

    NONE = "NONE"
    SIZE = "SIZE"
    TIME = "TIME"


"""logger config keys"""
# global config
LEVEL_KEY = "logger.level"
DRIVER_KEY = "logger.driver"

# console config
CONSOLE_ENABLED_KEY = "logger.console.enable"

# file logger
FILE_ENABLED_KEY = "logger.file.enable"
FILE_DIR_KEY = "logger.file.dir"
FILE_NAME_KEY = "logger.file.name"
FILE_ROTATE_KEY = "logger.file.rotate"
FILE_MAX_BYTES_KEY = "logger.file.maxbytes"
FILE_INTERVAL_KEY = "logger.file.interval"
FILE_BACKUP_COUNT_KEY = "logger.file.backupcount"

"""some logger default value"""
DEFAULT_DRIVER_VALUE = "logging"
DEFAULT_LEVEL_VALUE = Level.DEBUG
# console
DEFAULT_CONSOLE_ENABLED_VALUE = True
# file
DEFAULT_FILE_ENABLED_VALUE = False
DEFAULT_FILE_DIR_VALUE = os.path.expanduser("~")
DEFAULT_FILE_NAME_VALUE = "dubbo.log"
DEFAULT_FILE_MAX_BYTES_VALUE = 10 * 1024 * 1024
DEFAULT_FILE_INTERVAL_VALUE = 1
DEFAULT_FILE_BACKUP_COUNT_VALUE = 10
