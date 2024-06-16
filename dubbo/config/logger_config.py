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
from dataclasses import dataclass
from typing import Dict, Optional

from dubbo.common import extension
from dubbo.common.constants import LoggerConstants, LoggerFileRotateType, LoggerLevel
from dubbo.common.url import URL
from dubbo.logger import loggerFactory


@dataclass
class ConsoleLoggerConfig:
    """Console logger configuration"""

    # default is open console logger
    console_enabled: bool = LoggerConstants.LOGGER_CONSOLE_ENABLED_VALUE
    # default console formatter is None, use the global formatter
    console_formatter: Optional[str] = None

    def check(self):
        pass

    def dict(self) -> Dict[str, str]:
        return {
            LoggerConstants.LOGGER_CONSOLE_ENABLED_KEY: str(self.console_enabled),
            LoggerConstants.LOGGER_CONSOLE_FORMAT_KEY: self.console_formatter or "",
        }


@dataclass
class FileLoggerConfig:
    """File logger configuration"""

    # default is close file logger
    file_enabled: bool = LoggerConstants.LOGGER_FILE_ENABLED_VALUE
    # default file formatter is None, use the global formatter
    file_formatter: Optional[str] = None
    # default log file dir is user home dir
    file_dir: str = LoggerConstants.LOGGER_FILE_DIR_VALUE
    # default log file name is "dubbo.log"
    file_name: str = LoggerConstants.LOGGER_FILE_NAME_VALUE
    # default no rotate
    rotate: LoggerFileRotateType = LoggerFileRotateType.NONE
    # when rotate is SIZE, max_bytes is required, default 10M
    max_bytes: int = LoggerConstants.LOGGER_FILE_MAX_BYTES_VALUE
    # when rotate is TIME, interval is required, unit is day, default 1
    interval: int = LoggerConstants.LOGGER_FILE_INTERVAL_VALUE
    # when rotate is not NONE, backup_count is required, default 10
    backup_count: int = LoggerConstants.LOGGER_FILE_BACKUP_COUNT_VALUE

    def check(self) -> None:
        if self.file_enabled:
            if self.rotate == LoggerFileRotateType.SIZE and self.max_bytes < 0:
                raise ValueError("Max bytes can't be less than 0")
            elif self.rotate == LoggerFileRotateType.TIME and self.interval < 1:
                raise ValueError("Interval can't be less than 1")

    def dict(self) -> Dict[str, str]:
        return {
            LoggerConstants.LOGGER_FILE_ENABLED_KEY: str(self.file_enabled),
            LoggerConstants.LOGGER_FILE_FORMAT_KEY: self.file_formatter or "",
            LoggerConstants.LOGGER_FILE_DIR_KEY: self.file_dir,
            LoggerConstants.LOGGER_FILE_NAME_KEY: self.file_name,
            LoggerConstants.LOGGER_FILE_ROTATE_KEY: self.rotate.value,
            LoggerConstants.LOGGER_FILE_MAX_BYTES_KEY: str(self.max_bytes),
            LoggerConstants.LOGGER_FILE_INTERVAL_KEY: str(self.interval),
            LoggerConstants.LOGGER_FILE_BACKUP_COUNT_KEY: str(self.backup_count),
        }


class LoggerConfig:

    def __init__(
        self,
        driver: str = LoggerConstants.LOGGER_DRIVER_VALUE,
        level: LoggerLevel = LoggerConstants.LOGGER_LEVEL_VALUE,
        formatter: Optional[str] = None,
        console: ConsoleLoggerConfig = ConsoleLoggerConfig(),
        file: FileLoggerConfig = FileLoggerConfig(),
    ):
        # set global config
        self._driver = driver
        self._level = level
        self._formatter = formatter
        # set console config
        self._console = console
        self._console.check()
        # set file comfig
        self._file = file
        self._file.check()

    def get_url(self) -> URL:
        # get LoggerConfig parameters
        parameters: Dict[str, str] = {
            **self._console.dict(),
            **self._file.dict(),
            LoggerConstants.LOGGER_DRIVER_KEY: self._driver,
            LoggerConstants.LOGGER_LEVEL_KEY: self._level.value,
            LoggerConstants.LOGGER_FORMAT_KEY: self._formatter or "",
        }

        return URL(
            protocol=self._driver,
            host=self._level.value,
            port=None,
            parameters=parameters,
        )

    def init(self):
        # get logger_adapter and initialize loggerFactory
        logger_adapter = extension.get_logger_adapter(self._driver, self.get_url())
        loggerFactory.logger_adapter = logger_adapter
