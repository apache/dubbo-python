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

from dubbo.common.url import URL
from dubbo.extension import extensionLoader
from dubbo.logger import LoggerAdapter
from dubbo.logger import constants as logger_constants
from dubbo.logger import loggerFactory
from dubbo.logger.constants import Level


@dataclass
class FileLoggerConfig:
    """
    File logger configuration.
    :param rotate: File rotate type.
    :type rotate: logger_constants.FileRotateType
    :param file_formatter: File formatter.
    :type file_formatter: Optional[str]
    :param file_dir: File directory.
    :type file_dir: str
    :param file_name: File name.
    :type file_name: str
    :param backup_count: Backup count.
    :type backup_count: int
    :param max_bytes: Max bytes.
    :type max_bytes: int
    :param interval: Interval.
    :type interval: int
    """

    rotate: logger_constants.FileRotateType = logger_constants.FileRotateType.NONE
    file_formatter: Optional[str] = None
    file_dir: str = logger_constants.DEFAULT_FILE_DIR_VALUE
    file_name: str = logger_constants.DEFAULT_FILE_NAME_VALUE
    backup_count: int = logger_constants.DEFAULT_FILE_BACKUP_COUNT_VALUE
    max_bytes: int = logger_constants.DEFAULT_FILE_MAX_BYTES_VALUE
    interval: int = logger_constants.DEFAULT_FILE_INTERVAL_VALUE

    def check(self) -> None:
        if self.rotate == logger_constants.FileRotateType.SIZE and self.max_bytes < 0:
            raise ValueError("Max bytes can't be less than 0")
        elif self.rotate == logger_constants.FileRotateType.TIME and self.interval < 1:
            raise ValueError("Interval can't be less than 1")

    def dict(self) -> Dict[str, str]:
        return {
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
    """

    __slots__ = [
        "_driver",
        "_level",
        "_console_enabled",
        "_console_config",
        "_file_enabled",
        "_file_config",
    ]

    def __init__(
        self,
        driver,
        level: Level,
        console_enabled: bool,
        file_enabled: bool,
        file_config: FileLoggerConfig,
    ):
        """
        Initialize the logger configuration.
        :param driver: The logger driver.
        :type driver: str
        :param level: The logger level.
        :type level: Level
        :param console_enabled: Whether to enable console logger.
        :type console_enabled: bool
        :param file_enabled: Whether to enable file logger.
        :type file_enabled: bool
        :param file_config: The file logger configuration.
        :type file_config: FileLogger
        """
        # set global config
        self._driver = driver
        self._level = level
        # set console config
        self._console_enabled = console_enabled
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
            logger_constants.CONSOLE_ENABLED_KEY: str(self._console_enabled),
            logger_constants.FILE_ENABLED_KEY: str(self._file_enabled),
            **self._file_config.dict(),
        }

        return URL(scheme=self._driver, host=self._level.value, parameters=parameters)

    def init(self):
        # get logger_adapter and initialize loggerFactory
        logger_adapter_class = extensionLoader.get_extension(
            LoggerAdapter, self._driver
        )
        logger_adapter = logger_adapter_class(self.get_url())
        loggerFactory.set_logger_adapter(logger_adapter)

    @classmethod
    def default_config(cls):
        """
        Get default logger configuration.
        """
        return LoggerConfig(
            driver=logger_constants.DEFAULT_DRIVER_VALUE,
            level=logger_constants.DEFAULT_LEVEL_VALUE,
            console_enabled=logger_constants.DEFAULT_CONSOLE_ENABLED_VALUE,
            file_enabled=logger_constants.DEFAULT_FILE_ENABLED_VALUE,
            file_config=FileLoggerConfig(),
        )
