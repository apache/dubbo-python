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

from dubbo.common.constants.logger import Level
from dubbo.config import LoggerConfig
from dubbo.logger.internal.logger_adapter import InternalLoggerAdapter


class TestInternalLogger(unittest.TestCase):

    def test_log(self):
        logger_adapter = InternalLoggerAdapter(config=LoggerConfig("logging").get_url())
        logger = logger_adapter.get_logger("test")
        logger.log(Level.INFO, "test log")
        logger.debug("test debug")
        logger.info("test info")
        logger.warning("test warning")
        logger.error("test error")
        logger.critical("test critical")
        logger.fatal("test fatal")
        try:
            1 / 0
        except ZeroDivisionError:
            logger.exception("test exception")

        # test different default logger level
        logger_adapter.level = Level.INFO
        logger.debug("debug can't be logged")

        logger_adapter.level = Level.WARNING
        logger.info("info can't be logged")

        logger_adapter.level = Level.ERROR
        logger.warning("warning can't be logged")
