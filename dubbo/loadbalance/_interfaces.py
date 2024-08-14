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
from typing import List, Optional

from dubbo.protocol import Invocation, Invoker
from dubbo.url import URL


class LoadBalance(abc.ABC):
    """
    The load balance interface.
    """

    @abc.abstractmethod
    def select(
        self, invokers: List[Invoker], url: URL, invocation: Invocation
    ) -> Optional[Invoker]:
        """
        Select an invoker from the list.
        :param invokers: The invokers.
        :type invokers: List[Invoker]
        :param url: The URL.
        :type url: URL
        :param invocation: The invocation.
        :type invocation: Invocation
        :return: The selected invoker. If no invoker is selected, return None.
        :rtype: Optional[Invoker]
        """
        raise NotImplementedError()


class AbstractLoadBalance(LoadBalance, abc.ABC):
    """
    The abstract load balance.
    """

    def select(
        self, invokers: List[Invoker], url: URL, invocation: Invocation
    ) -> Optional[Invoker]:
        if not invokers:
            return None

        if len(invokers) == 1:
            return invokers[0]

        return self.do_select(invokers, url, invocation)

    @abc.abstractmethod
    def do_select(
        self, invokers: List[Invoker], url: URL, invocation: Invocation
    ) -> Optional[Invoker]:
        """
        Do select an invoker from the list.
        :param invokers: The invokers.
        :type invokers: List[Invoker]
        :param url: The URL.
        :type url: URL
        :param invocation: The invocation.
        :type invocation: Invocation
        :return: The selected invoker. If no invoker is selected, return None.
        :rtype: Optional[Invoker]
        """
        raise NotImplementedError()
