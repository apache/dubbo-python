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
from concurrent.futures import ThreadPoolExecutor

from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.logger.logger_factory import loggerFactory
from dubbo.protocol.invoker import Invoker
from dubbo.protocol.protocol import Protocol
from dubbo.protocol.triple.tri_invoker import TriInvoker
from dubbo.remoting.aio.h2_protocol import H2Protocol
from dubbo.remoting.aio.h2_stream_handler import ClientStreamHandler
from dubbo.remoting.transporter import Transporter
from dubbo.url import URL

logger = loggerFactory.get_logger(__name__)


class TripleProtocol(Protocol):

    def __init__(self, url: URL):
        self._url = url
        self._transporter: Transporter = extensionLoader.get_extension(
            Transporter,
            self._url.get_parameter(common_constants.TRANSPORTER_KEY) or "aio",
        )()
        self._invokers = []

    def refer(self, url: URL) -> Invoker:
        """
        Refer a remote service.
        Args:
            url (URL): The URL of the remote service.
        """
        # TODO Simply create it here, then set up a more appropriate configuration that can be configured by the user
        executor = ThreadPoolExecutor(thread_name_prefix="dubbo-tri-")
        # Create a stream handler
        stream_handler = ClientStreamHandler(executor)
        url.add_attribute("protocol", H2Protocol)
        url.add_attribute("stream_handler", stream_handler)
        # Create a client
        client = self._transporter.connect(url)
        invoker = TriInvoker(url, client, stream_handler)
        self._invokers.append(invoker)
        return invoker
