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
import os
from dataclasses import dataclass
from typing import Optional

from dubbo.logger import Level, RotateType


@dataclass
class ConsoleLoggerConfig:
    # default is open console logger
    enabled: bool = True
    # default level is None, use the global level
    level: Optional[Level] = None
    # default formatter is None, use the global formatter
    formatter: Optional[str] = None


@dataclass
class FileLoggerConfig:
    # default is close file logger
    enabled: bool = False
    # default level is None, use the global level
    level: Optional[Level] = None
    # default formatter is None, use the global formatter
    formatter: Optional[str] = None
    # default log file dir is user home dir
    file_dir: Optional[str] = os.path.expanduser("~")
    # default no rotate
    rotate: Optional[RotateType] = RotateType.NONE
    # when rotate is SIZE, max_bytes is required, default 10M
    max_bytes: Optional[int] = 1024 * 1024 * 10
    # when rotate is TIME, rotation is required, unit is day, default 1
    rotation: Optional[int] = 1
    # when rotate is not NONE, backup_count is required, default 10
    backup_count: Optional[int] = 10


class LoggerConfig:

    def __init__(
        self,
        logger: str = "internal",
        level: Level = Level.INFO,
        formatter: Optional[str] = None,
        console_config: ConsoleLoggerConfig = ConsoleLoggerConfig(),
        file_config: FileLoggerConfig = FileLoggerConfig(),
    ):
        # global logger config
        self._logger = logger
        self._default_level = level
        self._default_formatter = formatter
        # console logger config
        self._console_config = console_config
        # file logger config
        self._file_config = file_config

        self._set_default_config()

    def _set_default_config(self):
        # update console logger config
        if self._console_config.enabled:
            if self._console_config.level is None:
                self._console_config.level = self._default_level
            if self._console_config.formatter is None:
                self._console_config.formatter = self._default_formatter

        # update file logger config
        if self._file_config.enabled:
            if self._file_config.level is None:
                self._file_config.level = self._default_level
            if self._file_config.formatter is None:
                self._file_config.formatter = self._default_formatter
