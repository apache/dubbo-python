# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""Python-native Apache Dubbo: declare a service contract with `service`, then serve and call services with `Dubbo`.

``protoc-gen-python-dubbo`` generates contracts from proto files; see `dubbo.protoc`.
"""

from .application import Dubbo
from .exceptions import DubboError, EndOfStream, RemoteError, RpcError, Status
from .rpc import (
    BidiStream,
    ClientStream,
    GenericService,
    IncomingCall,
    Invocation,
    Invoke,
    Invoker,
    Method,
    OutgoingCall,
    Parameter,
    ReceiveStream,
    Result,
    RpcType,
    SendStream,
    ServerStream,
    Service,
    Stream,
    get_definition,
    incoming,
    method,
    outgoing,
    service,
)
from .url import URL

__all__ = [
    "URL",
    "BidiStream",
    "ClientStream",
    "Dubbo",
    "DubboError",
    "EndOfStream",
    "GenericService",
    "IncomingCall",
    "Invocation",
    "Invoke",
    "Invoker",
    "Method",
    "OutgoingCall",
    "Parameter",
    "ReceiveStream",
    "RemoteError",
    "Result",
    "RpcError",
    "RpcType",
    "SendStream",
    "ServerStream",
    "Service",
    "Status",
    "Stream",
    "get_definition",
    "incoming",
    "method",
    "outgoing",
    "service",
]
