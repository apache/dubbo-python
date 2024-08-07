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

from dubbo.common import constants as common_constants
from dubbo.common.deliverers import MultiMessageDeliverer, SingleMessageDeliverer
from dubbo.protocol import Result


class TriResult(Result):
    """
    The triple result.
    """

    def __init__(self, call_type: str):
        self._streamed = True
        if call_type in [
            common_constants.UNARY_CALL_VALUE,
            common_constants.CLIENT_STREAM_CALL_VALUE,
        ]:
            self._streamed = False

        self._deliverer = (
            MultiMessageDeliverer() if self._streamed else SingleMessageDeliverer()
        )

        self._exception = None

    def set_value(self, value: Any) -> None:
        """
        Set the value.
        """
        self._deliverer.add(value)

    def complete_value(self) -> None:
        """
        Complete the value.
        """
        self._deliverer.complete()

    def value(self) -> Any:
        """
        Get the value.
        """
        if self._streamed:
            return self._deliverer
        else:
            return self._deliverer.get()

    def set_exception(self, exception: Exception) -> None:
        """
        Set the exception.
        """
        self._exception = exception
        self._deliverer.cancel(exception)

    def exception(self) -> Exception:
        """
        Get the exception.
        """
        return self._exception
