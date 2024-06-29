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
import re
from enum import Enum


class Colors(Enum):
    """
    Colors for log messages.
    """

    END = "\033[0m"
    BOLD = "\033[1m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    PURPLE = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GREY = "\033[38;5;240m"


LEVEL_MAP = {
    "DEBUG": Colors.BLUE.value,
    "INFO": Colors.GREEN.value,
    "WARNING": Colors.YELLOW.value,
    "ERROR": Colors.RED.value,
    "CRITICAL": Colors.RED.value + Colors.BOLD.value,
}

DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

LOG_FORMAT: str = (
    f"{Colors.GREEN.value}%(asctime)s{Colors.END.value}"
    " | "
    f"%(level_color)s%(levelname)s{Colors.END.value}"
    " | "
    f"{Colors.CYAN.value}%(module)s:%(funcName)s:%(lineno)d{Colors.END.value}"
    " - "
    f"{Colors.PURPLE.value}[Dubbo]{Colors.END.value} "
    f"%(msg_color)s%(message)s{Colors.END.value}"
)


class ColorFormatter(logging.Formatter):
    """
    A formatter with color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    def __init__(self):
        self.log_format = LOG_FORMAT
        super().__init__(self.log_format, DATE_FORMAT)

    def format(self, record) -> str:
        levelname = record.levelname
        record.level_color = record.msg_color = LEVEL_MAP.get(levelname)
        return super().format(record)


class NoColorFormatter(logging.Formatter):
    """
    A formatter without color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    def __init__(self):
        color_re = re.compile(r"\033\[[0-9;]*\w|%\((msg_color|level_color)\)s")
        self.log_format = color_re.sub("", LOG_FORMAT)
        super().__init__(self.log_format, DATE_FORMAT)
