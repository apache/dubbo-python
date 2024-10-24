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
import threading
from typing import Dict, List

from dubbo.cluster.directories import RegistryDirectory
from dubbo.loggers import loggerFactory
from dubbo.protocol import Invoker, Protocol
from dubbo.protocol.invocation import RpcInvocation
from dubbo.proxy.handlers import RpcMethodHandler, RpcServiceHandler
from dubbo.registry import Registry
from dubbo.url import URL
from dubbo.utils import CpuUtils

_LOGGER = loggerFactory.get_logger()

_cpu_invocation = RpcInvocation(
    "org.apache.dubbo.MetricsService",
    "cpu",
    str(1).encode("utf-8"),
)


class CpuMonitor(RegistryDirectory):
    """
    The CPU monitor.
    """

    def __init__(self, registry: Registry, protocol: Protocol, url: URL):
        super().__init__(registry, protocol, url)

        # interval
        self._interval = 5

        # about CPU usage
        self._usages_lock = threading.Lock()
        self._cpu_usages: Dict[Invoker, float] = {}

        # running invokers
        self._running_invokers: Dict[str, Invoker] = {}

        # thread
        self._started = False
        self._thread: threading.Thread = threading.Thread(
            target=self._monitor_cpu, daemon=True
        )
        self._stop_event: threading.Event = threading.Event()

        # start the monitor
        self.start()

    def start(self) -> None:
        """
        Start the monitor.
        """
        if self._stop_event.is_set():
            raise RuntimeError("The monitor has been stopped.")
        elif self._started:
            return

        self._started = True
        self._thread.start()
        _LOGGER.info("The CPU monitor has been started.")

    def stop(self) -> None:
        """
        Stop the monitor.
        """
        if self._stop_event.is_set():
            return
        # notify the thread to stop
        self._stop_event.set()

    def _monitor_cpu(self) -> None:
        """
        Monitor the CPU usage.
        """
        while True:
            # get available invokers
            available_invokers = {
                url: invoker
                for url, invoker in self._invokers.items()
                if invoker.is_available()
            }

            # update the running invokers
            self._running_invokers = available_invokers

            # update the CPU usage
            with self._usages_lock:
                self._cpu_usages = {
                    invoker: usage
                    for invoker, usage in self._cpu_usages.items()
                    if invoker in available_invokers.values()
                }

            # get the CPU usage for each invoker
            for url, invoker in self._running_invokers.items():
                if invoker.is_available():
                    try:
                        result = invoker.invoke(_cpu_invocation)
                        cpu_usage = float(result.value().decode("utf-8"))
                        self._cpu_usages[invoker] = cpu_usage
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to get the CPU usage for invoker {url}: {str(e)}"
                        )
                        # remove the cpu usage
                        self._remove_cpu_usage(invoker)

            # wait for the interval or stop
            if self._stop_event.wait(self._interval):
                _LOGGER.info("The CPU monitor has been stopped.")
                break

    def get_cpu_usage(self, invokers: List[Invoker]) -> Dict[Invoker, float]:
        """
        Get the CPU usage for the invoker.
        :param invokers: The invokers.
        :type invokers: List[Invoker]
        :return: The CPU usage.
        :rtype: Dict[Invoker, float]
        """
        with self._usages_lock:
            return {invoker: self._cpu_usages.get(invoker, 0) for invoker in invokers}

    def _remove_cpu_usage(self, invoker: Invoker) -> None:
        with self._usages_lock:
            self._cpu_usages.pop(invoker)


class CpuInnerRpcHandler:
    """
    The CPU inner RPC handler.
    """

    @staticmethod
    def get_service_handler() -> RpcServiceHandler:
        """
        Get the service handler.
        :return: The service handler.
        :rtype: RpcServiceHandler
        """
        return RpcServiceHandler(
            "org.apache.dubbo.MetricsService",
            [
                RpcMethodHandler.unary(
                    CpuInnerRpcHandler.get_cpu_usage, method_name="cpu"
                ),
            ],
        )

    @staticmethod
    def get_cpu_usage(interval) -> bytes:
        """
        Get the CPU usage.
        :param interval: The interval.
        :type interval: bytes
        :return: The CPU usage.
        :rtype: bytes
        """
        float_value = CpuUtils.get_total_cpu_usage(
            interval=int(interval.decode("utf-8"))
        )
        return str(float_value).encode("utf-8")
