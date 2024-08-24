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

import socket

__all__ = ["EventHelper", "FutureHelper", "NetworkUtils"]

from typing import List, Tuple

import psutil


class EventHelper:
    """
    Helper class for event operations.
    """

    @staticmethod
    def is_set(event) -> bool:
        """
        Check if the event is set.

        :param event: Event object, you can use threading.Event or any other object that supports the is_set operation.
        :type event: Any
        :return: True if the event is set, or False if the is_set method is not supported or the event is invalid.
        :rtype: bool
        """
        return event.is_set() if event and hasattr(event, "is_set") else False

    @staticmethod
    def set(event) -> bool:
        """
        Attempt to set the event object.

        :param event: Event object, you can use threading.Event or any other object that supports the set operation.
        :type event: Any
        :return: True if the event was set, False otherwise
                (such as the event is invalid or does not support the set operation).
        :rtype: bool
        """
        if event is None:
            return False

        # If the event supports the set operation, set the event and return True
        if hasattr(event, "set"):
            event.set()
            return True

        # If the event is invalid or does not support the set operation, return False
        return False

    @staticmethod
    def clear(event) -> bool:
        """
        Attempt to clear the event object.

        :param event: Event object, you can use threading.Event or any other object that supports the clear operation.
        :type event: Any
        :return: True if the event was cleared, False otherwise
                (such as the event is invalid or does not support the clear operation).
        :rtype: bool
        """
        if not event:
            return False

        # If the event supports the clear operation, clear the event and return True
        if hasattr(event, "clear"):
            event.clear()
            return True

        # If the event is invalid or does not support the clear operation, return False
        return False


class FutureHelper:
    """
    Helper class for future operations.
    """

    @staticmethod
    def done(future) -> bool:
        """
        Check if the future is done.

        :param future: Future object
        :type future: Any
        :return: True if the future is done, False otherwise.
        :rtype: bool
        """
        return future.done() if future and hasattr(future, "done") else False

    @staticmethod
    def set_result(future, result):
        """
        Set the result of the future.

        :param future: Future object
        :type future: Any
        :param result: Result to set
        :type result: Any
        """
        if not future or FutureHelper.done(future):
            return

        if hasattr(future, "set_result"):
            future.set_result(result)

    @staticmethod
    def set_exception(future, exception):
        """
        Set the exception to the future.

        :param future: Future object
        :type future: Any
        :param exception: Exception to set
        :type exception: Exception
        """
        if not future or FutureHelper.done(future):
            return

        if hasattr(future, "set_exception"):
            future.set_exception(exception)


class NetworkUtils:
    """
    Helper class for network operations.
    """

    @staticmethod
    def get_host_name():
        """
        Get the host name of the host machine.

        :return: The host name of the host machine.
        :rtype: str
        """
        return socket.gethostname()

    @staticmethod
    def get_host_ip():
        """
        Get the IP address of the host machine.

        :return: The IP address of the host machine.
        :rtype: str
        """
        return socket.gethostbyname(NetworkUtils.get_host_name())


class CpuUtils:
    """
    Helper class for CPU operations.
    """

    @staticmethod
    def get_cpu_count(logical=True) -> int:
        """
        Get the number of CPUs in the system.

        :return: The number of CPUs in the system.
        :rtype: int
        """
        return psutil.cpu_count(logical=logical)

    @staticmethod
    def get_total_cpu_usage(interval=1) -> float:
        """
        Get the total CPU usage of the system.

        :param interval: The interval in seconds.
        :type interval: int
        :return: The total CPU usage of the system.
        :rtype: float
        """
        return psutil.cpu_percent(interval=interval)

    @staticmethod
    def get_per_cpu_usage(interval=1) -> List[float]:
        """
        Get the per CPU usage of the system.

        :param interval: The interval in seconds.
        :type interval: int
        :return: The per CPU usage of the system.
        :rtype: list
        """
        return psutil.cpu_percent(interval=interval, percpu=True)

    @staticmethod
    def get_load_avg() -> Tuple[float, float, float]:
        """
        Get the load average over the last 1, 5, and 15 minutes

        :return: The load average of the system.
        :rtype: list
        """
        return psutil.getloadavg()

    @staticmethod
    def get_cpu_stats():
        """
        Get the CPU stats of the system.

        :return: The CPU stats of the system.
        """
        return psutil.cpu_stats()

    @staticmethod
    def get_cpu_freq():
        """
        Get the current CPU frequency.

        :return: The current CPU frequency.
        """
        return psutil.cpu_freq()
