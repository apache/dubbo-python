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
from collections import namedtuple
from typing import Any, Callable

__all__ = [
    "SerializingFunction",
    "DeserializingFunction",
    "CallType",
    "UnaryCallType",
    "ClientStreamCallType",
    "ServerStreamCallType",
    "BiStreamCallType",
]

SerializingFunction = Callable[[Any], bytes]
DeserializingFunction = Callable[[bytes], Any]


# CallType
CallType = namedtuple("CallType", ["name", "client_stream", "server_stream"])
UnaryCallType = CallType("UnaryCall", False, False)
ClientStreamCallType = CallType("ClientStreamCall", True, False)
ServerStreamCallType = CallType("ServerStream", False, True)
BiStreamCallType = CallType("BiStreamCall", True, True)
