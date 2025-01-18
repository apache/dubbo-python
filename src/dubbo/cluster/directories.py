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

from dubbo.cluster import Directory
from dubbo.protocol import Invoker, Protocol
from dubbo.registry import NotifyListener, Registry
from dubbo.url import URL


class RegistryDirectory(Directory, NotifyListener):
    """
    The registry directory.
    """

    def __init__(self, registry: Registry, protocol: Protocol, url: URL):
        self._registry = registry
        self._protocol = protocol

        self._url = url

        self._invokers: dict[str, Invoker] = {}

        # subscribe
        self._registry.subscribe(url, self)

    def list(self, invocation) -> list[Invoker]:
        return list(self._invokers.values())

    def notify(self, urls: list[URL]) -> None:
        old_invokers = self._invokers
        self._invokers = {}

        # create new invokers
        for url in urls:
            k = str(url)
            if k in old_invokers.items():
                self._invokers[k] = old_invokers[k]
                del old_invokers[k]
            else:
                self._invokers[k] = self._protocol.refer(url)

        # destroy old invokers
        for invoker in old_invokers.values():
            invoker.destroy()

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._registry.is_available()

    def destroy(self) -> None:
        self._registry.destroy()
