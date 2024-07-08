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
from typing import List, Optional

from dubbo.config.method_config import MethodConfig
from dubbo.extension import extensionLoader
from dubbo.protocol.invoker import Invoker
from dubbo.protocol.protocol import Protocol
from dubbo.url import URL


class ReferenceConfig:

    _interface_name: str
    _check: bool
    _url: str
    _protocol: str
    _methods: List[MethodConfig]

    _global_lock: threading.Lock
    _initialized: bool
    _destroyed: bool
    _protocol_ins: Optional[Protocol]
    _invoker: Optional[Invoker]

    def __init__(
        self,
        interface_name: str,
        url: str,
        protocol: str,
        methods: Optional[List[MethodConfig]] = None,
    ):
        self._initialized = False
        self._global_lock = threading.Lock()
        self._destroyed = False
        self._interface_name = interface_name
        self._url = url
        self._protocol = protocol
        self._methods = methods or []

        self._invoker = None

    def get_invoker(self):
        if not self._invoker:
            self._do_init()
        return self._invoker

    def _do_init(self):
        with self._global_lock:
            if self._initialized:
                return

            clazz = extensionLoader.get_extension(Protocol, self._protocol)
            # TODO set real URL
            self._protocol_ins = clazz(URL.value_of(self._url))
            self._create_invoker()
            self._initialized = True

    def _create_invoker(self):
        url = URL.value_of(self._url)
        url.path = self._interface_name
        self._invoker = self._protocol_ins.refer(url)
