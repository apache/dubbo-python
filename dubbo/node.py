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

from dubbo.url import URL

__all__ = ["Node"]


class Node(abc.ABC):
    """
    Abstract base class for a Node.
    """

    @abc.abstractmethod
    def get_url(self) -> URL:
        """
        Get the URL of the node.

        :return: The URL of the node.
        :rtype: URL
        :raises NotImplementedError: If the method is not implemented.
        """
        raise NotImplementedError("get_url() is not implemented.")

    @abc.abstractmethod
    def is_available(self) -> bool:
        """
        Check if the node is available.

        :return: True if the node is available, False otherwise.
        :rtype: bool
        :raises NotImplementedError: If the method is not implemented.
        """
        raise NotImplementedError("is_available() is not implemented.")

    @abc.abstractmethod
    def destroy(self) -> None:
        """
        Destroy the node.

        :raises NotImplementedError: If the method is not implemented.
        """
        raise NotImplementedError("destroy() is not implemented.")
