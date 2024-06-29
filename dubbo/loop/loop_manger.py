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
import threading
from typing import Optional

from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


def start_loop(loop):
    """
    Start the loop.
    Args:
        loop: The loop to start.
    """
    asyncio.set_event_loop(loop)
    loop.run_forever()


class LoopManager:
    """
    Loop manager.
    It used to manage the global event loop and therefore designed as a singleton pattern.
    Attributes:
        _instance: The instance of the loop manager.
        _ins_lock: The lock to protect the instance.
        _client_initialized: Whether the client is initialized.
        _client_destroyed: Whether the client is destroyed.
        _client_loop_info: The client info. (thread, loop)
        _cli_lock: The lock to protect the client info.
    """

    _instance = None
    _ins_lock = threading.Lock()

    # About client
    _client_initialized = False
    _client_destroyed = False
    _client_loop_info = None
    _cli_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._ins_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _init_client_loop(self):
        """
        Initialize the client loop.
        return: The client info. (thread, loop)
        """
        new_loop = asyncio.new_event_loop()
        # Start the loop in a new thread
        thread = threading.Thread(
            target=start_loop, args=(new_loop,), name="dubbo-client-loop", daemon=True
        )
        thread.start()
        self._client_loop_info = (thread, new_loop)
        self._client_initialized = True
        logger.info("The client loop is initialized.")
        return self._client_loop_info

    def get_client_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Get the client loop. Lazy initialization.
        return: If the client is destroyed, return None. Otherwise, return the client loop.
        """
        if self._client_destroyed:
            logger.error("The client is destroyed.")
            return None

        if not self._client_initialized:
            with self._cli_lock:
                if not self._client_initialized:
                    self._init_client_loop()
        return self._client_loop_info[1]

    def destroy_client_loop(self) -> None:
        """
        Destroy the client. This method can only be called once.
        """
        if self._client_destroyed:
            logger.info("The client is already destroyed.")
            return

        with self._cli_lock:
            if not self._client_destroyed:
                client_loop_info = self._client_loop_info
                # Stop the loop
                client_loop_info[1].stop()
                # Wait for the loop to stop
                client_loop_info[0].join()
                self._client_destroyed = True
                logger.info("The client is destroyed.")
