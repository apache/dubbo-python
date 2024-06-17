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
from dubbo.common.constants import logger as logger_constants
from dubbo.common.constants.logger import FileRotateType, Level
from dubbo.common.url import URL
from dubbo.logger import loggerFactory


@dataclass
class ConsoleLoggerConfig:
    """
    Console logger configuration.
    Attributes:
        console_format(Optional[str]): console format, if null, use global format.
    """

    console_format: Optional[str] = None

    def check(self):
        pass

    def dict(self) -> Dict[str, str]:
        return {
            logger_constants.CONSOLE_FORMAT_KEY: self.console_format or "",
        }


@dataclass
class FileLoggerConfig:
    """
    File logger configuration.
    Attributes:
        rotate(FileRotateType): File rotate type. Optional: NONE,SIZE,TIME. Default: NONE.
        file_formatter(Optional[str]): file format, if null, use global format.
        file_dir(str): file directory. Default: user home dir
        file_name(str): file name. Default: dubbo.log
        backup_count(int): backup count. Default: 10 (when rotate is not NONE, backup_count is required)
        max_bytes(int): maximum file size. Default: 1024.(when rotate is SIZE, max_bytes is required)
        interval(int): interval time in seconds. Default: 1.(when rotate is TIME, interval is required, unit is day)

    """

    rotate: FileRotateType = FileRotateType.NONE
    file_formatter: Optional[str] = None
    file_dir: str = logger_constants.DEFAULT_FILE_DIR_VALUE
    file_name: str = logger_constants.DEFAULT_FILE_NAME_VALUE
    backup_count: int = logger_constants.DEFAULT_FILE_BACKUP_COUNT_VALUE
    max_bytes: int = logger_constants.DEFAULT_FILE_MAX_BYTES_VALUE
    interval: int = logger_constants.DEFAULT_FILE_INTERVAL_VALUE

    def check(self) -> None:
        if self.rotate == FileRotateType.SIZE and self.max_bytes < 0:
            raise ValueError("Max bytes can't be less than 0")
        elif self.rotate == FileRotateType.TIME and self.interval < 1:
            raise ValueError("Interval can't be less than 1")

    def dict(self) -> Dict[str, str]:
        return {
            logger_constants.FILE_FORMAT_KEY: self.file_formatter or "",
            logger_constants.FILE_DIR_KEY: self.file_dir,
            logger_constants.FILE_NAME_KEY: self.file_name,
            logger_constants.FILE_ROTATE_KEY: self.rotate.value,
            logger_constants.FILE_MAX_BYTES_KEY: str(self.max_bytes),
            logger_constants.FILE_INTERVAL_KEY: str(self.interval),
            logger_constants.FILE_BACKUP_COUNT_KEY: str(self.backup_count),
        }


class LoggerConfig:
    """
    Logger configuration.

    Attributes:
        _driver(str): logger driver type.
        _level(Level): logger level.
        _formatter(Optional[str]): logger formatter.
        _console_enabled(bool): logger console enabled.
        _console_config(ConsoleLoggerConfig): logger console config.
        _file_enabled(bool): logger file enabled.
        _file_config(FileLoggerConfig): logger file config.
    """

    # global
    _driver: str
    _level: Level
    _formatter: Optional[str]
    # console
    _console_enabled: bool
    _console_config: ConsoleLoggerConfig
    # file
    _file_enabled: bool
    _file_config: FileLoggerConfig

    def __init__(
        self,
        driver,
        level=logger_constants.DEFAULT_LEVEL_VALUE,
        formatter: Optional[str] = None,
        console_enabled: bool = logger_constants.DEFAULT_CONSOLE_ENABLED_VALUE,
        console_config: ConsoleLoggerConfig = ConsoleLoggerConfig(),
        file_enabled: bool = logger_constants.DEFAULT_FILE_ENABLED_VALUE,
        file_config: FileLoggerConfig = FileLoggerConfig(),
    ):
        # set global config
        self._driver = driver
        self._level = level
        self._formatter = formatter
        # set console config
        self._console_enabled = console_enabled
        self._console_config = console_config
        if console_enabled:
            self._console_config.check()
        # set file comfig
        self._file_enabled = file_enabled
        self._file_config = file_config
        if file_enabled:
            self._file_config.check()

    def get_url(self) -> URL:
        # get LoggerConfig parameters
        parameters = {
            logger_constants.DRIVER_KEY: self._driver,
            logger_constants.LEVEL_KEY: self._level.value,
            logger_constants.FORMAT_KEY: self._formatter or "",
            logger_constants.CONSOLE_ENABLED_KEY: str(self._console_enabled),
            logger_constants.FILE_ENABLED_KEY: str(self._file_enabled),
            **self._console_config.dict(),
            **self._file_config.dict(),
        }

        return URL(protocol=self._driver, host=self._level.value, parameters=parameters)

    def init(self):
        # get logger_adapter and initialize loggerFactory
        logger_adapter = extension.get_logger_adapter(self._driver, self.get_url())
        loggerFactory.logger_adapter = logger_adapter
