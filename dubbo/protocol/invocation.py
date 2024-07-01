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
from typing import Any


class Invocation:

    def get_service_name(self) -> str:
        """
        Get the service name.
        """
        raise NotImplementedError("get_service_name() is not implemented.")

    def get_method_name(self) -> str:
        """
        Get the method name.
        """
        raise NotImplementedError("get_method_name() is not implemented.")

    def get_argument(self) -> Any:
        """
        Get the method argument.
        """
        raise NotImplementedError("get_args() is not implemented.")


class RpcInvocation(Invocation):
    """
    The RpcInvocation class is an implementation of the Invocation interface.
    Args:
        service_name (str): The name of the service.
        method_name (str): The name of the method.
        argument (Any): The method argument.
        req_serializer (Any): The request serializer.
        res_serializer (Any): The response serializer.
    """

    def __init__(
        self,
        service_name: str,
        method_name: str,
        argument: Any,
        req_serializer=None,
        res_serializer=None,
    ):
        self._service_name = service_name
        self._method_name = method_name
        self._argument = argument
        self._req_serializer = req_serializer
        self._res_serializer = res_serializer

    def get_service_name(self):
        return self._service_name

    def get_method_name(self):
        return self._method_name

    def get_argument(self):
        return self._argument

    def get_req_serializer(self):
        return self._req_serializer

    def get_res_serializer(self):
        return self._res_serializer
