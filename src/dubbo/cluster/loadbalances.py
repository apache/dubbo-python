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
import abc
import random
from typing import Optional

from dubbo.cluster import LoadBalance
from dubbo.cluster.monitor.cpu import CpuMonitor
from dubbo.protocol import Invocation, Invoker


class AbstractLoadBalance(LoadBalance, abc.ABC):
    """
    The abstract load balance.
    """

    def select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        if not invokers:
            return None

        if len(invokers) == 1:
            return invokers[0]

        return self.do_select(invokers, invocation)

    @abc.abstractmethod
    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        """
        Do select an invoker from the list.
        :param invokers: The invokers.
        :type invokers: List[Invoker]
        :param invocation: The invocation.
        :type invocation: Invocation
        :return: The selected invoker. If no invoker is selected, return None.
        :rtype: Optional[Invoker]
        """
        raise NotImplementedError()


class RandomLoadBalance(AbstractLoadBalance):
    """
    Random load balance.
    """

    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        randint = random.randint(0, len(invokers) - 1)
        return invokers[randint]


class CpuLoadBalance(AbstractLoadBalance):
    """
    CPU load balance.
    """

    def __init__(self):
        self._monitor: Optional[CpuMonitor] = None

    def set_monitor(self, monitor: CpuMonitor) -> None:
        """
        Set the CPU monitor.
        :param monitor: The CPU monitor.
        :type monitor: CpuMonitor
        """
        self._monitor = monitor

    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        # get the CPU usage
        cpu_usages = self._monitor.get_cpu_usage(invokers)
        # Select the caller with the lowest CPU usage, 0 means CPU usage is unknown.
        available_invokers = []
        unknown_invokers = []

        for invoker, cpu_usage in cpu_usages.items():
            if cpu_usage == 0:
                unknown_invokers.append((cpu_usage, invoker))
            else:
                available_invokers.append((cpu_usage, invoker))

        if available_invokers:
            # sort and select the invoker with the lowest CPU usage
            available_invokers.sort(key=lambda x: x[0])
            return available_invokers[0][1]
        elif unknown_invokers:
            # get the invoker with unknown CPU usage randomly
            randint = random.randint(0, len(unknown_invokers) - 1)
            return unknown_invokers[randint][1]
        else:
            return None
