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


class Result:
    """
    Result of a call
    """

    def set_value(self, value: Any) -> None:
        """
        Set the value of the result
        Args:
            value: Value to set
        """
        raise NotImplementedError("set_value() is not implemented.")

    def value(self) -> Any:
        """
        Get the value of the result
        """
        raise NotImplementedError("get_value() is not implemented.")

    def set_exception(self, exception: Exception) -> None:
        """
        Set the exception to the result
        Args:
            exception: Exception to set
        """
        raise NotImplementedError("set_exception() is not implemented.")

    def exception(self) -> Exception:
        """
        Get the exception to the result
        """
        raise NotImplementedError("get_exception() is not implemented.")

    def add_attachment(self, key: str, value: Any) -> None:
        """
        Add an attachment to the result
        Args:
            key: Key of the attachment
            value: Value of the attachment
        """
        raise NotImplementedError("add_attachment() is not implemented.")

    def get_attachment(self, key: str) -> Any:
        """
        Get an attachment from the result
        Args:
            key: Key of the attachment
        """
        raise NotImplementedError("get_attachment() is not implemented.")
