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

from typing import Optional

from dubbo.common import URL
from dubbo.common import constants as common_constants
from dubbo.extension import extensionLoader
from dubbo.protocol import Protocol
from dubbo.proxy.handlers import RpcServiceHandler

__all__ = ["ServiceConfig"]


class ServiceConfig:
    """
    Service configuration
    """

    def __init__(
        self,
        service_handler: RpcServiceHandler,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
    ):

        self._service_handler = service_handler
        self._port = port or common_constants.DEFAULT_PORT

        protocol_str = protocol or common_constants.TRIPLE_SHORT

        self._export_url = URL(
            protocol_str, common_constants.LOCAL_HOST_KEY, self._port
        )
        self._export_url.attributes[common_constants.SERVICE_HANDLER_KEY] = (
            service_handler
        )

        self._protocol: Protocol = extensionLoader.get_extension(
            Protocol, protocol_str
        )(self._export_url)

        self._exported = False
        self._exporting = False

    def export(self):
        """
        Export service
        """
        if self._exporting or self._exported:
            return

        self._exporting = True
        try:
            self._protocol.export(self._export_url)
            self._exported = True
        finally:
            self._exporting = False
