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
import uuid
from typing import Optional

from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


def _try_use_uvloop() -> None:
    """
    Use uvloop instead of the default asyncio running_loop.
    """
    import asyncio
    import os

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

    # Use uvloop instead of the default asyncio running_loop.
    if not isinstance(asyncio.get_event_loop_policy(), uvloop.EventLoopPolicy):
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


# Call the function to try to use uvloop.
_try_use_uvloop()


class EventLoop:

    def __init__(self, in_other_tread: bool = True):
        self._in_other_tread = in_other_tread
        # The event loop to run the asynchronous function.
        self._loop = asyncio.new_event_loop()
        # The thread to run the event loop.
        self._thread: Optional[threading.Thread] = (
            None if in_other_tread else threading.current_thread()
        )

        self._started = False
        self._stopped = False

        # The lock to protect the event loop.
        self._lock = threading.Lock()

    @property
    def loop(self):
        """
        Get the event loop.
        Returns:
            The event loop.
        """
        return self._loop

    @property
    def thread(self) -> Optional[threading.Thread]:
        """
        Get the thread of the event loop.
        Returns:
            The thread of the event loop. If not yet started, this is None.
        """
        return self._thread

    def check_thread(self) -> bool:
        """
        Check if the current thread is the event loop thread.
        Returns:
            If the current thread is the event loop thread, return True. Otherwise, return False.
        """
        return threading.current_thread().ident == self._thread.ident

    def is_started(self) -> bool:
        """
        Check if the event loop is started.
        """
        return self._started

    def start(self):
        """
        Start the asyncio event loop.
        """
        if self._started:
            return
        with self._lock:
            self._started = True
            self._stopped = False
            if self._in_other_tread:
                self._start_in_thread()
            else:
                self._start()

    def _start(self) -> None:
        """
        Real start the asyncio event loop in current thread.
        """
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _start_in_thread(self) -> None:
        """
        Real Start the asyncio event loop in a separate thread.
        """
        thread_name = f"dubbo-asyncio-loop-{str(uuid.uuid4())}"
        thread = threading.Thread(target=self._start, name=thread_name, daemon=True)
        thread.start()
        self._thread = thread

    def stop(self, wait: bool = False) -> None:
        """
        Stop the asyncio event loop.
        """
        if self._stopped:
            return
        with self._lock:
            signal = threading.Event()
            asyncio.run_coroutine_threadsafe(self._stop(signal=signal), self._loop)
            # Wait for the running_loop to stop
            if wait:
                signal.wait()
                if self._in_other_tread:
                    self._thread.join()
            self._stopped = True
            self._started = False

    async def _stop(self, signal: threading.Event) -> None:
        """
        Real stop the asyncio event loop.
        """
        # Cancel all tasks
        tasks = [
            task
            for task in asyncio.all_tasks(self._loop)
            if task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Stop the event running_loop
        self._loop.stop()
        # Set the signal
        signal.set()
