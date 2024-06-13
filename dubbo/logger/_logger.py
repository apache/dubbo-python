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
from typing import Any


class Logger:
    """
    Logger Interface, which is used to log messages.
    All loggers should implement this interface.
    """

    def __init__(self, name: str, *args, **kwargs):
        """
        Initialize the logger.
        """
        pass

    @classmethod
    def get_logger(cls, name: str) -> "Logger":
        """
        Get the logger by name.
        """
        raise NotImplementedError("get_logger() is not implemented.")

    def log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a message.
        """
        raise NotImplementedError("log() is not implemented.")

    def debug(self, msg: str, *args, **kwargs) -> None:
        """
        Log a debug message.
        """
        raise NotImplementedError("debug() is not implemented.")

    def info(self, msg: str, *args, **kwargs) -> None:
        """
        Log an info message.
        """
        raise NotImplementedError("info() is not implemented.")

    def warning(self, msg: str, *args, **kwargs) -> None:
        """
        Log a warning message.
        """
        raise NotImplementedError("warning() is not implemented.")

    def error(self, msg: str, *args, **kwargs) -> None:
        """
        Log an error message.
        """
        raise NotImplementedError("error() is not implemented.")

    def critical(self, msg: str, *args, **kwargs) -> None:
        """
        Log a critical message.
        """
        raise NotImplementedError("critical() is not implemented.")

    def fatal(self, msg: str, *args, **kwargs) -> None:
        """
        Log a fatal message.
        """
        raise NotImplementedError("fatal() is not implemented.")

    def exception(self, msg: str, *args, **kwargs) -> None:
        """
        Log an exception message.
        """
        raise NotImplementedError("exception() is not implemented.")
