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
import unittest

from dubbo.common.constants import LoggerConstants, LoggerLevel
from dubbo.config import LoggerConfig
from dubbo.logger import loggerFactory
from dubbo.logger.internal.logger_adapter import InternalLoggerAdapter


class TestLoggerFactory(unittest.TestCase):

    def test_without_config(self):
        # Test the case where config is not used
        logger = loggerFactory.get_logger("test_factory")
        logger.info("info log -> without_config ")

    def test_with_config(self):
        # Test the case where config is used
        config = LoggerConfig()
        config.init()
        logger = loggerFactory.get_logger("test_factory")
        logger.info("info log -> with_config ")

        url = config.get_url()
        url.add_parameter(LoggerConstants.LOGGER_FILE_ENABLED_KEY, True)
        loggerFactory.set_logger_adapter(InternalLoggerAdapter(url))
        loggerFactory.set_level(LoggerLevel.DEBUG)
        logger.debug("debug log -> with_config -> open file")

        url.add_parameter(LoggerConstants.LOGGER_CONSOLE_ENABLED_KEY, False)
        loggerFactory.set_logger_adapter(InternalLoggerAdapter(url))
        loggerFactory.set_level(LoggerLevel.DEBUG)
        logger.debug("debug log -> with_config -> lose console")
