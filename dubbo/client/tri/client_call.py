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


class UnaryUnaryMultiCallable(abc.ABC):
    """Affords invoking a unary-unary RPC from client-side."""

    @abc.abstractmethod
    def __call__(
            self,
            request,
            timeout=None,
            compression=None
    ):
        """
        Synchronously invokes the underlying RPC.
        Args:
          request: The request value for the RPC.
          timeout: An optional duration of time in seconds to allow for the RPC.
          compression: An element of dubbo.common.compression, e.g. 'gzip'.
        """

        raise NotImplementedError()
