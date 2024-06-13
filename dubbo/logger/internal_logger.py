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
from typing import Any, Dict

from dubbo.common import extension
from dubbo.logger import Logger


@extension.register_logger(name="internal")
class InternalLogger(Logger):

    _loggers: Dict[str, "InternalLogger"] = {}

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self._logger = logging.getLogger(name)
        # Set the default log format.
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(module)s:%(funcName)s:%(lineno)d - [Dubbo] %(message)s"
        )
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    @classmethod
    def get_logger(cls, name: str) -> "Logger":
        logger_instance = cls._loggers.get(name, None)
        if logger_instance is None:
            logger_instance = cls(name)
            cls._loggers[name] = logger_instance
        return logger_instance

    def log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._logger.critical(msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs) -> None:
        self._logger.fatal(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        self._logger.exception(msg, *args, **kwargs)
