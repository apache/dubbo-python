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

from dubbo.cluster import Cluster, Directory, LoadBalance
from dubbo.cluster.loadbalances import CpuLoadBalance
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Invoker, Result
from dubbo.protocol.triple.exceptions import RpcError
from dubbo.url import URL


class FailfastInvoker(Invoker):
    """
    FailfastInvoker
    """

    def __init__(self, directory, url: URL):
        self._directory = directory

        self._load_balance = extensionLoader.get_extension(
            LoadBalance, url.parameters.get(common_constants.LOADBALANCE_KEY, "random")
        )()

        if isinstance(self._load_balance, CpuLoadBalance):
            self._load_balance.set_monitor(directory)

    def invoke(self, invocation) -> Result:
        # get the invokers
        invokers = self._directory.list(invocation)
        if not invokers:
            raise RpcError("No provider available for the service")

        # select the invoker
        invoker = self._load_balance.select(invokers, invocation)

        # invoke the invoker
        return invoker.invoke(invocation)

    def get_url(self) -> URL:
        return self._directory.get_url()

    def is_available(self) -> bool:
        return self._directory.is_available()

    def destroy(self):
        self._directory.destroy()


class FailfastCluster(Cluster):
    """
    Execute exactly once, which means this policy will throw an exception immediately in case of an invocation error.
    Usually used for non-idempotent write operations
    """

    def join(self, directory: Directory) -> Invoker:
        return FailfastInvoker(directory, directory.get_url())
