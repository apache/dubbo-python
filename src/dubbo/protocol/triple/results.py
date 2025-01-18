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

from dubbo.protocol import Result


class TriResult(Result):
    """
    The triple result.
    """

    __slots__ = ["_future"]

    def __init__(self, future):
        self._future = future

    def set_value(self, value: Any) -> None:
        """
        Set the value.
        """
        self._future.set_result(value)

    def value(self) -> Any:
        """
        Get the value.
        """
        return self._future.result()

    def set_exception(self, exception: Exception) -> None:
        """
        Set the exception.
        """
        self._future.set_exception(exception)

    def exception(self) -> Exception:
        """
        Get the exception.
        """
        return self._future.exception()
