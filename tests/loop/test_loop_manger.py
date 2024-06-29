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
import asyncio
import unittest

from dubbo.loop.loop_manger import LoopManager


async def _loop_task():
    while True:
        print("loop task")
        await asyncio.sleep(1)


class TestLoopManager(unittest.TestCase):

    def test_use_client(self):
        loop_manager = LoopManager()
        loop = loop_manager.get_client_loop()
        asyncio.run_coroutine_threadsafe(_loop_task(), loop)
        print("loop task started, waiting for 3 seconds...")
        asyncio.run(asyncio.sleep(3))
        loop_manager.destroy_client_loop()
        print("loop task stopped.")
