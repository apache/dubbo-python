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
import threading
from typing import Any, Optional, Union

from dubbo.classes import EOF, ReadStream, ReadWriteStream, WriteStream
from dubbo.protocol.triple.call import ClientCall, ServerCall
from dubbo.protocol.triple.constants import GRpcCode
from dubbo.protocol.triple.exceptions import RpcError
from dubbo.protocol.triple.status import TriRpcStatus


class TriReadStream(ReadStream):
    """
    Triple read stream. Support reading data from the stream.
    """

    __slots__ = ["_storage", "_lock", "_read_done"]

    def __init__(self):
        self._read_done = False
        self._storage = queue.Queue(maxsize=1000)
        self._lock = threading.RLock()

    def put(self, data: Any) -> None:
        """
        Put data into the stream. It is private and should not be called by the user.
        :param data: The data to put into the stream.
        :type data: Any
        """
        if self._read_done:
            return
        self._storage.put_nowait(data)

    def put_eof(self) -> None:
        """
        Put EOF into the stream. It is private and should not be called by the user.
        """
        if self._read_done:
            return
        self._read_done = True
        self._storage.put_nowait(EOF)

    def put_exception(self, e: Exception) -> None:
        """
        Set an exception to the stream. It is private and should not be called by the user.
        :param e: The exception to set.
        :type e: Exception
        """
        # Stop the read stream
        self.put_eof()
        # Raise the exception
        raise e

    def read(self, timeout: Optional[int] = None) -> Any:
        """
        Read the stream.
        :param timeout:
            The timeout in seconds. If None, it will block until the data is available.
        :type timeout: Optional[int]
        :return:
            The data read from the stream.
            If no more data, return EOF.
            If no data available within the timeout, return None.
        :rtype: Any
        """
        # If you can't read more data, return EOF
        if self._read_done and self._storage.empty():
            return EOF

        try:
            data = self._storage.get(timeout=max(0, timeout) if timeout is not None else None)
            return data
        except queue.Empty:
            return None

    def __iter__(self):
        return self

    def __next__(self):
        data = self.read()
        if data is EOF:
            raise StopIteration
        return data


class TriClientWriteStream(WriteStream):
    """
    Triple client write stream. Support writing data to the stream.
    """

    __slots__ = ["_call", "_write_done"]

    def __init__(self, call: Optional[ClientCall] = None):
        self._call: Optional[ClientCall] = call
        self._write_done = False

    def set_call(self, call: ClientCall):
        self._call = call

    def can_write_more(self) -> bool:
        """
        Check if the stream can write more data.
        :return: True if the stream can write more data, False otherwise.
        :rtype: bool
        """
        return not self._write_done

    def write(self, *args, **kwargs) -> None:
        """
        Write data to the stream.
        :param args: The arguments to pass to the write method.
        :param kwargs: The keyword arguments to pass to the write method.
        :raises RpcError: If write after done writing.
        """
        if self._write_done:
            raise RpcError("Write after done writing")
        self._call.send_message((args, kwargs), False)

    def done_writing(self, **kwargs) -> None:
        """
        Done writing to the stream.
        :raises RpcError: If done writing multiple times.
        """
        if self._write_done:
            raise RpcError("Done writing multiple times")

        self._call.send_message(None, True)
        self._write_done = True


class TriServerWriteStream(WriteStream):
    """
    Triple server write stream. Support writing data to the stream.
    """

    __slots__ = ["_call", "_write_done"]

    def __init__(self, call: ServerCall):
        self._call = call
        self._write_done = False

    def can_write_more(self) -> bool:
        """
        Check if the stream can write more data.
        :return: True if the stream can write more data, False otherwise.
        :rtype: bool
        """
        return not self._write_done

    def write(self, *args, **kwargs) -> None:
        """
        Write data to the stream.
        :param args: The arguments to pass to the write method.
        :param kwargs: The keyword arguments to pass to the write method.
        :raises RpcError: If write after done writing.
        """
        if self._write_done:
            raise RpcError("Write after done writing")
        self._call.send_message((args, kwargs))

    def done_writing(self, **kwargs) -> None:
        """
        Done writing to the stream.
        :param kwargs: The keyword arguments to pass to the done
        :raises RpcError: If done writing multiple times.
        """
        if self._write_done:
            raise RpcError("Done writing multiple times")

        # try to get TriRpcStatus from kwargs
        status = kwargs.get("tri_rpc_status")
        if status is None:
            status = TriRpcStatus(GRpcCode.OK)
        elif not isinstance(status, TriRpcStatus):
            raise RpcError("Invalid status type")

        # remove the status from kwargs
        kwargs.pop("tri-rpc-status", None)

        self._call.complete(status, kwargs)
        self._write_done = True


class TriReadWriteStream(ReadWriteStream):
    """
    Triple client read write stream. Support reading and writing data from the stream.
    """

    __slots__ = ["_read_stream", "_write_stream"]

    def __init__(
        self,
        write_stream: Union[TriClientWriteStream, TriServerWriteStream],
        read_stream: TriReadStream,
    ):
        """
        Initialize the read write stream.
        :param write_stream: The write stream.
        :type write_stream: TriClientWriteStream
        :param read_stream: The read stream.
        :type read_stream: TriReadStream
        """
        self._read_stream = read_stream
        self._write_stream = write_stream

    def can_write_more(self) -> bool:
        """
        Check if the stream can write more data.
        :return: True if the stream can write more data, False otherwise.
        :rtype: bool
        """
        if self._write_stream is None:
            raise RpcError("Write stream is not set")
        return self._write_stream.can_write_more()

    def can_read_more(self) -> bool:
        """
        Check if there is more data to read.
        :return: True if there is more data to read, False otherwise.
        :rtype: bool
        """
        if self._read_stream is None:
            raise RpcError("Read stream is not set")
        return self._read_stream.can_read_more()

    def read(self, timeout: Optional[int] = None) -> Any:
        """
        Read the stream.
        :param timeout:
            The timeout in seconds. If None, it will block until the data is available.
        :type timeout: Optional[int]
        :return:
            The data read from the stream.
            If no more data, return EOF.
            If no data available within the timeout, return None.
        :rtype: Any
        """
        if self._read_stream is None:
            raise RpcError("Read stream is not set")
        return self._read_stream.read(timeout)

    def write(self, *args, **kwargs) -> None:
        """
        Write data to the stream.
        :param args: The arguments to pass to the write method.
        :param kwargs: The keyword arguments to pass to the write method.
        :raises RpcError: If write after done writing.
        """
        if self._write_stream is None:
            raise RpcError("Write stream is not set")
        self._write_stream.write(*args, **kwargs)

    def done_writing(self, **kwargs) -> None:
        """
        Done writing to the stream.
        :raises RpcError: If done writing multiple times.
        """
        if self._write_stream is None:
            raise RpcError("Write stream is not set")
        self._write_stream.done_writing(**kwargs)

    def __iter__(self):
        return self

    def __next__(self):
        data = self.read()
        if data is EOF:
            raise StopIteration
        return data
