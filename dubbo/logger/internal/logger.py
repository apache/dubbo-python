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

import logging
from typing import Dict

from dubbo.common.constants.logger import Level
from dubbo.logger import Logger

# The mapping from the logging level to the internal logging level.
_level_map: Dict[Level, int] = {
    Level.DEBUG: logging.DEBUG,
    Level.INFO: logging.INFO,
    Level.WARNING: logging.WARNING,
    Level.ERROR: logging.ERROR,
    Level.CRITICAL: logging.CRITICAL,
    Level.FATAL: logging.FATAL,
}


class InternalLogger(Logger):
    """
    The internal logger implementation.
    Attributes:
        _logger (logging.Logger): The real working logger object
    """

    _logger: logging.Logger

    def __init__(self, internal_logger: logging.Logger):
        self._logger = internal_logger

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        # Add the stacklevel to the keyword arguments.
        kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 2
        self._logger.log(level, msg, *args, **kwargs)

    def log(self, level: Level, msg: str, *args, **kwargs) -> None:
        self._log(_level_map[level], msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.FATAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        if kwargs.get("exc_info") is None:
            kwargs["exc_info"] = True
        self.error(msg, *args, **kwargs)

    def is_enabled_for(self, level: Level) -> bool:
        logging_level = _level_map.get(level)
        return self._logger.isEnabledFor(logging_level) if logging_level else False
