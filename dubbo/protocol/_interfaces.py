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

import abc
from typing import Any

from dubbo.common.node import Node
from dubbo.common.url import URL

__all__ = ["Invocation", "Result", "Invoker", "Protocol"]


class Invocation(abc.ABC):

    @abc.abstractmethod
    def get_service_name(self) -> str:
        """
        Get the service name.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_method_name(self) -> str:
        """
        Get the method name.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_argument(self) -> Any:
        """
        Get the method argument.
        """
        raise NotImplementedError()


class Result(abc.ABC):
    """
    Result of a call
    """

    @abc.abstractmethod
    def set_value(self, value: Any) -> None:
        """
        Set the value of the result
        Args:
            value: Value to set
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def value(self) -> Any:
        """
        Get the value of the result
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def set_exception(self, exception: Exception) -> None:
        """
        Set the exception to the result
        Args:
            exception: Exception to set
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def exception(self) -> Exception:
        """
        Get the exception to the result
        """
        raise NotImplementedError()


class Invoker(Node, abc.ABC):
    """
    Invoker
    """

    @abc.abstractmethod
    def invoke(self, invocation: Invocation) -> Result:
        """
        Invoke the service.
        Returns:
            Result: The result of the invocation.
        """
        raise NotImplementedError()


class Protocol(abc.ABC):

    @abc.abstractmethod
    def export(self, url: URL):
        """
        Export a remote service.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def refer(self, url: URL) -> Invoker:
        """
        Refer a remote service.
        Args:
            url (URL): The URL of the remote service.
        Returns:
            Invoker: The invoker of the remote service.
        """
        raise NotImplementedError()
