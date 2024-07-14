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
from typing import Optional, Union

from dubbo.extension import extensionLoader
from dubbo.protocol.invoker import Invoker
from dubbo.protocol.protocol import Protocol
from dubbo.url import URL


class ReferenceConfig:

    __slots__ = [
        "_initialized",
        "_global_lock",
        "_service_name",
        "_url",
        "_protocol",
        "_invoker",
    ]

    def __init__(self, url: Union[str, URL], service_name: str):
        self._initialized = False
        self._global_lock = threading.Lock()
        self._url: URL = url if isinstance(url, URL) else URL.value_of(url)
        self._service_name = service_name
        self._protocol: Optional[Protocol] = None
        self._invoker: Optional[Invoker] = None

    def get_invoker(self) -> Invoker:
        if not self._invoker:
            self._do_init()
        return self._invoker

    def _do_init(self):
        with self._global_lock:
            if self._initialized:
                return
            # Get the interface name from the URL path
            self._url.path = self._service_name
            self._protocol = extensionLoader.get_extension(Protocol, self._url.scheme)(
                self._url
            )
            self._create_invoker()
            self._initialized = True

    def _create_invoker(self):
        self._invoker = self._protocol.refer(self._url)
