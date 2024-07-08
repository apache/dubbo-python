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
from typing import Optional, Tuple

from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


def start_loop(running_loop: asyncio.AbstractEventLoop) -> None:
    """
    Start the running_loop.
    Args:
        running_loop: The running_loop to start.
    """
    asyncio.set_event_loop(running_loop)
    running_loop.run_forever()


async def _stop_loop(
    running_loop: Optional[asyncio.AbstractEventLoop] = None,
    signal: Optional[threading.Event] = None,
) -> None:
    """
    Real function to stop the running_loop.
    Args:
        running_loop: The running_loop to stop. If None, the current running_loop will be stopped.
        signal: The future to set the result.
    """
    running_loop = running_loop or asyncio.get_running_loop()
    # Cancel all tasks
    tasks = [
        task for task in asyncio.all_tasks(running_loop) if task is not asyncio.current_task()
    ]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    # Stop the event running_loop
    running_loop.stop()
    if signal:
        # Set the result of the future
        signal.set()


def stop_loop(running_loop: Optional[asyncio.AbstractEventLoop] = None, wait: bool = False):
    """
    Stop the running_loop. It will cancel all tasks and stop the running_loop.(thread-safe)
    Args:
        running_loop: The running_loop to stop. If None, the current running_loop will be stopped.
        wait: Whether to wait for the running_loop to stop.
    """
    running_loop = running_loop or asyncio.get_running_loop()
    # Create a future to wait for the running_loop to stop
    signal = threading.Event()
    # Call the asynchronous function to stop the running_loop
    asyncio.run_coroutine_threadsafe(_stop_loop(signal=signal), running_loop)
    if wait:
        # Wait for the running_loop to stop
        signal.wait()


def start_loop_in_thread(
    thread_name: str, running_loop: Optional[asyncio.AbstractEventLoop] = None
) -> Tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """
    start the asyncio event running_loop in a separate thread.

    Args:
        thread_name: The name of the thread to run the event running_loop in.
        running_loop: The event running_loop to run in the thread. If None, a new event running_loop will be created.

    Returns:
        A tuple containing the new event running_loop and the thread it is running in.
    """
    new_loop = running_loop or asyncio.new_event_loop()
    # Start the running_loop in a new thread
    thread = threading.Thread(
        target=start_loop, args=(new_loop,), name=thread_name, daemon=True
    )
    # Start the thread
    thread.start()
    return new_loop, thread


def stop_loop_in_thread(
    running_loop: asyncio.AbstractEventLoop, thread: threading.Thread, wait: bool = False
) -> None:
    """
    Stop the event running_loop running in a separate thread and close the thread.

    Args:
        running_loop: The event running_loop to stop.
        thread: The thread running the event running_loop.
        wait: Whether to wait for all tasks to be cancelled and the running_loop to stop.
    """
    stop_loop(running_loop, wait=wait)
    # Wait for the thread to join
    if wait:
        print("等待线程结束")
        thread.join()


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
