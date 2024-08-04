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
import enum
import queue
import threading
from typing import Any, Optional

__all__ = ["MessageDeliverer", "SingleMessageDeliverer", "MultiMessageDeliverer"]


class DelivererStatus(enum.Enum):
    """
    Enumeration for deliverer status.

    Possible statuses:
        - PENDING: The deliverer is pending action.
        - COMPLETED: The deliverer has completed the action.
        - CANCELLED: The action for the deliverer has been cancelled.
        - FINISHED: The deliverer has finished all actions and is in a final state.
    """

    PENDING = 0
    COMPLETED = 1
    CANCELLED = 2
    FINISHED = 3

    @classmethod
    def change_allowed(
        cls, current_status: "DelivererStatus", target_status: "DelivererStatus"
    ) -> bool:
        """
        Check if a transition from `current_status` to `target_status` is allowed.

        :param current_status: The current status of the deliverer.
        :type current_status: DelivererStatus
        :param target_status: The target status to transition to.
        :type target_status: DelivererStatus
        :return: A boolean indicating if the transition is allowed.
        :rtype: bool
        """
        # PENDING -> COMPLETED or CANCELLED
        if current_status == cls.PENDING:
            return target_status in {cls.COMPLETED, cls.CANCELLED}

        # COMPLETED -> FINISHED or CANCELLED
        elif current_status == cls.COMPLETED:
            return target_status in {cls.FINISHED, cls.CANCELLED}

        # CANCELLED -> FINISHED
        elif current_status == cls.CANCELLED:
            return target_status == cls.FINISHED

        # FINISHED is the final state, no further transitions allowed
        else:
            return False


class NoMoreMessageError(RuntimeError):
    """
    Exception raised when no more messages are available.
    """

    def __init__(self, message: str = "No more message"):
        super().__init__(message)


class EmptyMessageError(RuntimeError):
    """
    Exception raised when the message is empty.
    """

    def __init__(self, message: str = "Message is empty"):
        super().__init__(message)


class MessageDeliverer(abc.ABC):
    """
    Abstract base class for message deliverers.
    """

    __slots__ = ["_status"]

    def __init__(self):
        self._status = DelivererStatus.PENDING

    @abc.abstractmethod
    def add(self, message: Any) -> None:
        """
        Add a message to the deliverer.

        :param message: The message to be added.
        :type message: Any
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def complete(self, message: Any = None) -> None:
        """
        Mark the message delivery as complete.

        :param message: The last message (optional).
        :type message: Any, optional
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel(self, exc: Optional[Exception]) -> None:
        """
        Cancel the message delivery.

        :param exc: The exception that caused the cancellation.
        :type exc: Exception, optional
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self) -> Any:
        """
        Get the next message.

        :return: The next message.
        :rtype: Any
        :raises NoMoreMessageError: If no more messages are available.
        :raises Exception: If the message delivery is cancelled.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_nowait(self) -> Any:
        """
        Get the next message without waiting.

        :return: The next message.
        :rtype: Any
        :raises EmptyMessageError: If the message is empty.
        :raises NoMoreMessageError: If no more messages are available.
        :raises Exception: If the message delivery is cancelled.
        """
        raise NotImplementedError()


class SingleMessageDeliverer(MessageDeliverer):
    """
    Message deliverer for a single message using a signal-based approach.
    """

    __slots__ = ["_condition", "_message"]

    def __init__(self):
        super().__init__()
        self._condition = threading.Condition()
        self._message: Any = None

    def add(self, message: Any) -> None:
        with self._condition:
            if self._status is DelivererStatus.PENDING:
                # Add the message
                self._message = message

    def complete(self, message: Any = None) -> None:
        with self._condition:
            if DelivererStatus.change_allowed(self._status, DelivererStatus.COMPLETED):
                if message is not None:
                    self._message = message
                # update the status
                self._status = DelivererStatus.COMPLETED
                self._condition.notify_all()

    def cancel(self, exc: Optional[Exception]) -> None:
        with self._condition:
            if DelivererStatus.change_allowed(self._status, DelivererStatus.CANCELLED):
                # Cancel the delivery
                self._message = exc or RuntimeError("delivery cancelled.")
                self._status = DelivererStatus.CANCELLED
                self._condition.notify_all()

    def get(self) -> Any:
        with self._condition:
            if self._status is DelivererStatus.FINISHED:
                raise NoMoreMessageError("Message already consumed.")

            if self._status is DelivererStatus.PENDING:
                # If the message is not available, wait
                self._condition.wait()

            # check the status
            if self._status is DelivererStatus.CANCELLED:
                raise self._message

            self._status = DelivererStatus.FINISHED
            return self._message

    def get_nowait(self) -> Any:
        with self._condition:
            if self._status is DelivererStatus.FINISHED:
                self._status = DelivererStatus.PENDING
                return self._message

            # raise error
            if self._status is DelivererStatus.FINISHED:
                raise NoMoreMessageError("Message already consumed.")
            elif self._status is DelivererStatus.CANCELLED:
                raise self._message
            elif self._status is DelivererStatus.PENDING:
                raise EmptyMessageError("Message is empty")


class MultiMessageDeliverer(MessageDeliverer):
    """
    Message deliverer supporting multiple messages.
    """

    __slots__ = ["_lock", "_counter", "_messages", "_END_SENTINEL"]

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._counter = 0
        self._messages: queue.PriorityQueue[Any] = queue.PriorityQueue()
        self._END_SENTINEL = object()

    def add(self, message: Any) -> None:
        with self._lock:
            if self._status is DelivererStatus.PENDING:
                # Add the message
                self._counter += 1
                self._messages.put_nowait((self._counter, message))

    def complete(self, message: Any = None) -> None:
        with self._lock:
            if DelivererStatus.change_allowed(self._status, DelivererStatus.COMPLETED):
                if message is not None:
                    self._counter += 1
                    self._messages.put_nowait((self._counter, message))

                # Add the end sentinel
                self._counter += 1
                self._messages.put_nowait((self._counter, self._END_SENTINEL))
                self._status = DelivererStatus.COMPLETED

    def cancel(self, exc: Optional[Exception]) -> None:
        with self._lock:
            if DelivererStatus.change_allowed(self._status, DelivererStatus.CANCELLED):
                # Set the priority to -1 -> make sure it is the first message
                self._messages.put_nowait(
                    (-1, exc or RuntimeError("delivery cancelled."))
                )
                self._status = DelivererStatus.CANCELLED

    def get(self) -> Any:
        if self._status is DelivererStatus.FINISHED:
            raise NoMoreMessageError("No more message")

        # block until the message is available
        priority, message = self._messages.get()

        # check the status
        if self._status is DelivererStatus.CANCELLED:
            raise message
        elif message is self._END_SENTINEL:
            self._status = DelivererStatus.FINISHED
            raise NoMoreMessageError("No more message")
        else:
            return message

    def get_nowait(self) -> Any:
        try:
            if self._status is DelivererStatus.FINISHED:
                raise NoMoreMessageError("No more message")

            priority, message = self._messages.get_nowait()

            # check the status
            if self._status is DelivererStatus.CANCELLED:
                raise message
            elif message is self._END_SENTINEL:
                self._status = DelivererStatus.FINISHED
                raise NoMoreMessageError("No more message")
            else:
                return message
        except queue.Empty:
            raise EmptyMessageError("Message is empty")

    def __iter__(self):
        return self

    def __next__(self):
        """
        Returns the next request from the queue.

        :return: The next message.
        :rtype: Any
        :raises StopIteration: If no more messages are available.
        """
        while True:
            try:
                return self.get()
            except NoMoreMessageError:
                raise StopIteration
