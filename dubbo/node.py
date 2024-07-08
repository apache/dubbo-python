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
from dubbo.url import URL


class Node:
    """
    Node
    """

    def get_url(self) -> URL:
        """
        Get the url of the node
        Returns:
            URL: URL of the node
        """
        raise NotImplementedError("get_url() is not implemented.")

    def is_available(self) -> bool:
        """
        Check if the node is available
        Returns:
            bool: True if the node is available, false otherwise
        """
        raise NotImplementedError("is_available() is not implemented.")

    def destroy(self) -> None:
        """
        Destroy the node
        """
        raise NotImplementedError("destroy() is not implemented.")
