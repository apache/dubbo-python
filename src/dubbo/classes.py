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
import threading
from typing import Any, Callable, Optional, Union

from dubbo.types import DeserializingFunction, RpcType, RpcTypes, SerializingFunction

__all__ = [
    "EOF",
    "SingletonBase",
    "MethodDescriptor",
    "ReadStream",
    "WriteStream",
    "ReadWriteStream",
]


class _EOF:
    """
    EOF is a class representing the end flag.
    """

    _repr_str = "<dubbo.classes.EOF>"

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __repr__(self) -> str:
        return self._repr_str

    def __str__(self) -> str:
        return self._repr_str


# The EOF object -> global constant
EOF = _EOF()


class SingletonBase:
    """
    Singleton base class. This class ensures that only one instance of a derived class exists.

    This implementation is thread-safe.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        Create a new instance of the class if it does not exist.
        """
        if cls._instance is None:
            with cls._instance_lock:
                # double check
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance


class MethodDescriptor:
    """
    MethodDescriptor is a descriptor for a method.
    It contains the method name, the method, and the method's serialization and deserialization methods.
    """

    __slots__ = [
        "_callable_method",
        "_method_name",
        "_rpc_type",
        "_arg_serialization",
        "_return_serialization",
    ]

    def __init__(
        self,
        method_name: str,
        arg_serialization: tuple[Optional[SerializingFunction], Optional[DeserializingFunction]],
        return_serialization: tuple[Optional[SerializingFunction], Optional[DeserializingFunction]],
        rpc_type: Union[RpcType, RpcTypes, str] = RpcTypes.UNARY.value,
        callable_method: Optional[Callable] = None,
    ):
        """
        Initialize the method model.

        :param method_name:
            The name of the method.
        :type method_name: str

        :param arg_serialization:
            A tuple containing serialization and deserialization methods for the function's arguments.
        :type arg_serialization: Optional[Tuple[SerializingFunction, DeserializingFunction]]

        :param return_serialization:
            A tuple containing serialization and deserialization methods for the function's return values.
        :type return_serialization: Optional[Tuple[SerializingFunction, DeserializingFunction]]

        :param rpc_type:
            The RPC type. default is RpcTypes.UNARY.
        :type rpc_type: RpcType

        :param callable_method:
            The main callable method to be executed.
        :type callable_method: Optional[Callable]
        """
        self._method_name = method_name
        self._arg_serialization = arg_serialization
        self._return_serialization = return_serialization
        self._callable_method = callable_method

        if isinstance(rpc_type, str):
            rpc_type = RpcTypes.from_name(rpc_type)
        elif isinstance(rpc_type, RpcTypes):
            rpc_type = rpc_type.value
        elif not isinstance(rpc_type, RpcType):
            raise TypeError(f"rpc_type must be of type RpcType, RpcTypes, or str, not {type(rpc_type)}")
        self._rpc_type = rpc_type

    def get_method(self) -> Callable:
        """
        Get the callable method.
        :return: The callable method.
        :rtype: Callable
        """
        return self._callable_method

    def get_method_name(self) -> str:
        """
        Get the method name.
        :return: The method name.
        :rtype: str
        """
        return self._method_name

    def get_rpc_type(self) -> RpcType:
        """
        Get the RPC type.
        :return: The RPC type.
        :rtype: RpcType
        """
        return self._rpc_type

    def get_arg_serializer(self) -> Optional[SerializingFunction]:
        """
        Get the argument serializer.
        :return: The argument serializer. If not set, return None.
        :rtype: Optional[SerializingFunction]
        """
        return self._arg_serialization[0] if self._arg_serialization else None

    def get_arg_deserializer(self) -> Optional[DeserializingFunction]:
        """
        Get the argument deserializer.
        :return: The argument deserializer. If not set, return None.
        :rtype: Optional[DeserializingFunction]
        """
        return self._arg_serialization[1] if self._arg_serialization else None

    def get_return_serializer(self) -> Optional[SerializingFunction]:
        """
        Get the return value serializer.
        :return: The return value serializer. If not set, return None.
        :rtype: Optional[SerializingFunction]
        """
        return self._return_serialization[0] if self._return_serialization else None

    def get_return_deserializer(self) -> Optional[DeserializingFunction]:
        """
        Get the return value deserializer.
        :return: The return value deserializer. If not set, return None.
        :rtype: Optional[DeserializingFunction]
        """
        return self._return_serialization[1] if self._return_serialization else None


class ReadStream(abc.ABC):
    """
    ReadStream is an abstract class for reading streams.
    """

    @abc.abstractmethod
    def read(self, *args, **kwargs) -> Any:
        """
        Read the stream.
        :param args: The arguments to pass to the read method.
        :param kwargs: The keyword arguments to pass to the read method.
        :return: The read value.
        """
        raise NotImplementedError()


class WriteStream(abc.ABC):
    """
    WriteStream is an abstract class for writing streams.
    """

    @abc.abstractmethod
    def can_write_more(self) -> bool:
        """
        Check if the stream can write more data.
        :return: True if the stream can write more data, False otherwise.
        :rtype: bool
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def write(self, *args, **kwargs) -> None:
        """
        Write to the stream.
        :param args: The arguments to pass to the write method.
        :param kwargs: The keyword arguments to pass to the write method.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def done_writing(self, **kwargs) -> None:
        """
        Done writing to the stream.
        :param kwargs: The keyword arguments to pass to the done
        """
        raise NotImplementedError()


class ReadWriteStream(ReadStream, WriteStream, abc.ABC):
    """
    ReadWriteStream is an abstract class for reading and writing streams.
    """

    pass
