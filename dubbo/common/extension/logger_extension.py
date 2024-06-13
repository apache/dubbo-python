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
from typing import Dict, Type

from dubbo.logger import Logger

# A dictionary to store all the logger classes.
_logger_dict: Dict[str, Type[Logger]] = {}


def register_logger(name: str):
    """
    A decorator to register a logger class to the logger extension point.
    """

    def decorator(cls):
        _logger_dict[name] = cls
        return cls

    return decorator


def get_logger(name: str, *args, **kwargs) -> Logger:
    """
    Get a logger instance by name.
    """
    logger_cls = _logger_dict[name]
    return logger_cls(*args, **kwargs)
