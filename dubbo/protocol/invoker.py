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
from dubbo.common.node import Node
from dubbo.protocol.invocation import Invocation
from dubbo.protocol.result import Result


class Invoker(Node):

    def get_interface(self):
        """
        Get service interface.
        """
        raise NotImplementedError("get_interface() is not implemented.")

    def invoke(self, invocation: Invocation) -> Result:
        """
        Invoke the service.
        Returns:
            Result: The result of the invocation.
        """
        raise NotImplementedError("invoke() is not implemented.")
