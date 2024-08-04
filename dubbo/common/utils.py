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

__all__ = ["EventHelper", "FutureHelper"]


class EventHelper:
    """
    Helper class for event operations.
    """

    @staticmethod
    def is_set(event) -> bool:
        """
        Check if the event is set.

        :param event: Event object, you can use threading.Event or any other object that supports the is_set operation.
        :type event: Any
        :return: True if the event is set, or False if the is_set method is not supported or the event is invalid.
        :rtype: bool
        """
        return event.is_set() if event and hasattr(event, "is_set") else False

    @staticmethod
    def set(event) -> bool:
        """
        Attempt to set the event object.

        :param event: Event object, you can use threading.Event or any other object that supports the set operation.
        :type event: Any
        :return: True if the event was set, False otherwise
                (such as the event is invalid or does not support the set operation).
        :rtype: bool
        """
        if event is None:
            return False

        # If the event supports the set operation, set the event and return True
        if hasattr(event, "set"):
            event.set()
            return True

        # If the event is invalid or does not support the set operation, return False
        return False

    @staticmethod
    def clear(event) -> bool:
        """
        Attempt to clear the event object.

        :param event: Event object, you can use threading.Event or any other object that supports the clear operation.
        :type event: Any
        :return: True if the event was cleared, False otherwise
                (such as the event is invalid or does not support the clear operation).
        :rtype: bool
        """
        if not event:
            return False

        # If the event supports the clear operation, clear the event and return True
        if hasattr(event, "clear"):
            event.clear()
            return True

        # If the event is invalid or does not support the clear operation, return False
        return False


class FutureHelper:
    """
    Helper class for future operations.
    """

    @staticmethod
    def done(future) -> bool:
        """
        Check if the future is done.

        :param future: Future object
        :type future: Any
        :return: True if the future is done, False otherwise.
        :rtype: bool
        """
        return future.done() if future and hasattr(future, "done") else False

    @staticmethod
    def set_result(future, result):
        """
        Set the result of the future.

        :param future: Future object
        :type future: Any
        :param result: Result to set
        :type result: Any
        """
        if not future or FutureHelper.done(future):
            return

        if hasattr(future, "set_result"):
            future.set_result(result)

    @staticmethod
    def set_exception(future, exception):
        """
        Set the exception to the future.

        :param future: Future object
        :type future: Any
        :param exception: Exception to set
        :type exception: Exception
        """
        if not future or FutureHelper.done(future):
            return

        if hasattr(future, "set_exception"):
            future.set_exception(exception)
