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
import queue
from typing import Any, Dict, Optional

from dubbo.constants.common_constants import CALL_CLIENT_STREAM, CALL_UNARY
from dubbo.protocol.result import Result


class AbstractTriResult(Result):
    """
    The abstract result.
    """

    END_SIGNAL = object()

    def __init__(self, call_type: str):
        self.call_type = call_type
        self._exception: Optional[Exception] = None
        self._attachments: Dict[str, Any] = {}

    def set_exception(self, exception: Exception) -> None:
        self._exception = exception

    def exception(self) -> Exception:
        return self._exception

    def add_attachment(self, key: str, value: Any) -> None:
        self._attachments[key] = value

    def get_attachment(self, key: str) -> Any:
        return self._attachments.get(key)


class TriResult(AbstractTriResult):
    """
    The triple result.
    """

    def __init__(self, call_type: str):
        super().__init__(call_type)
        self._values = queue.Queue()

    def set_value(self, value: Any) -> None:
        """
        Set the value.
        """
        self._values.put(value)

    def value(self) -> Any:
        """
        Get the value.
        """
        if self.call_type in [CALL_UNARY, CALL_CLIENT_STREAM]:
            return self._get_single_value()
        else:
            return self._iterating_values()

    def _get_single_value(self) -> Any:
        """
        Get the single value.
        """
        return value if (value := self._values.get()) is not self.END_SIGNAL else None

    def _iterating_values(self) -> Any:
        """
        Iterate the values.
        """
        return iter(lambda: self._values.get(), self.END_SIGNAL)
