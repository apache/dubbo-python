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

__all__ = ["ConnectionStateListener", "EmptyConnectionStateListener"]


class ConnectionStateListener(abc.ABC):
    """
    Connection state listener. It is used to listen to the connection state.
    """

    @abc.abstractmethod
    async def connection_made(self):
        """
        Called when the connection is first established.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def connection_lost(self, exc):
        """
        Called when the connection is lost.
        """
        raise NotImplementedError()


class EmptyConnectionStateListener(ConnectionStateListener):
    """
    An empty connection state listener. It does nothing.
    """

    async def connection_made(self):
        pass

    async def connection_lost(self, exc):
        pass
