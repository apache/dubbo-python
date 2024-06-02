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

from dubbo.common import extension
from dubbo import logger


class TestExtension(unittest.TestCase):

    def test_get_instance(self):
        manager = extension.get_extension_manager()
        assert manager is not None
        loader = manager.get_extension_loader(logger.Logger)
        assert loader is not None
        dubbo_logger = loader.get_instance("loguru")
        assert dubbo_logger is not None
