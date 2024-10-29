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
import os
import socket
from collections.abc import Callable
from typing import Any, List, Tuple, Optional

import psutil
import inspect

__all__ = ["EventHelper", "FutureHelper", "NetworkUtils", "CpuUtils", "FunctionHelper"]


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
    def is_address_reachable(ip: str, timeout: int = 0) -> bool:
        """
        Use ping to check if the IP address is reachable.

        :param ip: The IP address.
        :type ip: str
        :param timeout: The timeout in seconds.
        :type timeout: int
        :return: True if the IP address is reachable, False otherwise.
        :rtype: bool
        """
        try:
            # Use the ping command to check if the IP address is reachable
            result = os.system(f"ping -c 1 -W {timeout} {ip} > /dev/null 2>&1")
            return result == 0
        except Exception:
            return False

    @staticmethod
    def is_loopback_address(ip: str) -> bool:
        """
        Check if the IP address is a loopback address.

        :param ip: The IP address.
        :type ip: str
        :return: True if the IP address is a loopback address, False otherwise.
        :rtype: bool
        """
        return ip.startswith("127.") or ip == "localhost"

    @staticmethod
    def get_local_address() -> Optional[str]:
        """
        Find first valid IP from local network card.

        :return: The local IP address. If not found, return None.
        :rtype: str
        """
        try:
            # use psutil to get the local IP address
            for iface_name, iface_addrs in psutil.net_if_addrs().items():
                for addr in iface_addrs:
                    # only consider IPv4 address
                    if addr.family == socket.AF_INET:
                        # ignore the loopback address and check if the IP address is reachable
                        if not NetworkUtils.is_loopback_address(
                            addr.address
                        ) and NetworkUtils.is_address_reachable(addr.address):
                            return addr.address
        except Exception:
            pass

        # if the local IP address is not found, try to get the IP address using the socket
        try:
            local_host_ip = socket.gethostbyname(socket.gethostname())
            return local_host_ip
        except Exception:
            pass

        return None


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


class FunctionHelper:
    """
    Helper class for function operations.
    """

    @staticmethod
    def is_callable(callable_func: Callable) -> bool:
        """
        Check if the function is callable.

        :param callable_func: The callable function.
        :type callable_func: Callable
        :return: True if the function is callable, False otherwise.
        :rtype: bool
        """
        return inspect.isfunction(callable_func) or inspect.ismethod(callable_func)

    @staticmethod
    def has_args(func: Callable) -> bool:
        """
        Check if the function has arguments.

        :param func: The callable function.
        :type func: Callable
        :return: True if the function has arguments, False otherwise.
        :rtype: bool
        """
        return inspect.Parameter.VAR_POSITIONAL in [
            p.kind for p in inspect.signature(func).parameters.values()
        ]

    @staticmethod
    def has_kwargs(func: Callable) -> bool:
        """
        Check if the function has keyword arguments.

        :param func: The callable function.
        :type func: Callable
        :return: True if the function has keyword arguments, False otherwise.
        :rtype: bool
        """
        return inspect.Parameter.VAR_KEYWORD in [
            p.kind for p in inspect.signature(func).parameters.values()
        ]

    @staticmethod
    def call_func(func: Callable, args_and_kwargs: Any = None) -> Any:
        """
        Call the function with the given arguments and keyword arguments.

        :param func:
            The callable function.
        :type func: Callable
        :param args_and_kwargs:
            The arguments and keyword arguments.

            the provided values must follow these forms:
            - No arguments required, pass -> None
            - Multiple positional arguments -> Tuple (e.g., ((1, 2),{}))
            - Multiple keyword arguments -> Dict (e.g., ((),{"a": 1, "b": 2}))
            - Both positional and keyword arguments -> Tuple of length 2
                (e.g., ((1, 2), {"a": 1, "b": 2}))

        :type args_and_kwargs: Tuple
        :return: The result of the function.
        :rtype: Any
        """

        # split the arguments and keyword arguments
        if isinstance(args_and_kwargs, tuple) and len(args_and_kwargs) == 2:
            args, kwargs = args_and_kwargs
        else:
            raise ValueError(
                "Invalid function arguments, the provided values must follow these forms:"
                "1.No arguments required, pass -> None"
                "2.Multiple positional arguments -> Tuple (e.g., ((1, 2),{}))"
                "3.Multiple keyword arguments -> Dict (e.g., ((),{'a': 1, 'b': 2}))"
                "4.Both positional and keyword arguments -> Tuple of length 2"
                " (e.g., ((1, 2), {'a': 1, 'b': 2}))"
            )

        # If the function is not callable, try to call the function directly
        try:
            if not FunctionHelper.is_callable(func):
                return func(*args, **kwargs)
        except Exception as e:
            raise e

        # Get the function signature
        sig = inspect.signature(func)

        # Get the function parameters and check if the function supports *args and **kwargs
        params = sig.parameters
        param_kinds = [p.kind for p in params.values()]
        has_var_positional = inspect.Parameter.VAR_POSITIONAL in param_kinds
        has_var_keyword = inspect.Parameter.VAR_KEYWORD in param_kinds

        # If the function has no arguments or only one argument, call the function directly
        if len(params) == 0 or args_and_kwargs is None:
            return func()

        # If the function accepts both *args and **kwargs
        if has_var_positional and has_var_keyword:
            return func(*args, **kwargs)

        # If the function supports *args but not **kwargs
        if has_var_positional:
            return func(*args)

        # If the function supports **kwargs but not *args
        if has_var_keyword:
            return func(**kwargs)

        # common case
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        return func(*bound_args.args, **bound_args.kwargs)
