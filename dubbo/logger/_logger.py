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

class Logger:
    """
    Logger Interface, which is used to log messages.
    All loggers should implement this interface.
    """

    def log(self, level: str, msg: str) -> None:
        """
        Log
        """
        raise NotImplementedError("Method 'log' is not implemented.")

    def debug(self, msg: str) -> None:
        """
        Debug log
        """
        raise NotImplementedError("Method 'debug' is not implemented.")

    def info(self, msg: str) -> None:
        """
        Info log
        """
        raise NotImplementedError("Method 'info' is not implemented.")

    def warning(self, msg: str) -> None:
        """
        Warning log
        """
        raise NotImplementedError("Method 'warning' is not implemented.")

    def error(self, msg: str) -> None:
        """
        Error log
        """
        raise NotImplementedError("Method 'error' is not implemented.")

    def critical(self, msg: str) -> None:
        """
        Critical log
        """
        raise NotImplementedError("Method 'critical' is not implemented.")

    def exception(self, msg: str) -> None:
        """
        Exception log
        """
        raise NotImplementedError("Method 'exception' is not implemented.")


# global logger, default logger is Logger(), so it will raise an error if it is not set
_LOGGER: Logger = Logger()


def set_logger(logger: Logger) -> None:
    """
    Set global logger
    """
    global _LOGGER
    if logger is not None and isinstance(logger, Logger):
        _LOGGER = logger
    else:
        raise ValueError("Invalid logger")


def set_logger_by_name(logger_name: str) -> None:
    """
    Set global logger by name
    """
    # import extension module here to avoid circular import
    from dubbo.common import extension
    extension_manager = extension.get_extension_manager()
    instance = extension_manager.get_extension_loader(Logger).get_instance(logger_name)
    set_logger(instance)


def get_logger() -> Logger:
    """
    Get global logger
    """
    return _LOGGER
