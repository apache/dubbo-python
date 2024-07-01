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

from dubbo.loop.loop_manger import LoopManager as _LoopManager


def _try_use_uvloop() -> None:
    """
    Use uvloop instead of the default asyncio loop.
    """
    import asyncio
    import os

    from dubbo.logger.logger_factory import loggerFactory

    logger = loggerFactory.get_logger("try_use_uvloop")

    # Check if the operating system.
    if os.name == "nt":
        # Windows is not supported.
        logger.warning(
            "Unable to use uvloop, because it is not supported on your operating system."
        )
        return

    # Try import uvloop.
    try:
        import uvloop
    except ImportError:
        # uvloop is not available.
        logger.warning(
            "Unable to use uvloop, because it is not installed. "
            "You can install it by running `pip install uvloop`."
        )
        return

    # Use uvloop instead of the default asyncio loop.
    if not isinstance(asyncio.get_event_loop_policy(), uvloop.EventLoopPolicy):
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


# Call the function to try to use uvloop.
_try_use_uvloop()

loopManager = _LoopManager()
