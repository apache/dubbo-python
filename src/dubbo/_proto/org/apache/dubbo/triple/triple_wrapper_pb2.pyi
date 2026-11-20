from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TripleRequestWrapper(_message.Message):
    __slots__ = ("serializeType", "args", "argTypes")
    SERIALIZETYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    ARGTYPES_FIELD_NUMBER: _ClassVar[int]
    serializeType: str
    args: _containers.RepeatedScalarFieldContainer[bytes]
    argTypes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, serializeType: _Optional[str] = ..., args: _Optional[_Iterable[bytes]] = ..., argTypes: _Optional[_Iterable[str]] = ...) -> None: ...

class TripleResponseWrapper(_message.Message):
    __slots__ = ("serializeType", "data", "type")
    SERIALIZETYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    serializeType: str
    data: bytes
    type: str
    def __init__(self, serializeType: _Optional[str] = ..., data: _Optional[bytes] = ..., type: _Optional[str] = ...) -> None: ...

class TripleExceptionWrapper(_message.Message):
    __slots__ = ("language", "serialization", "className", "data")
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SERIALIZATION_FIELD_NUMBER: _ClassVar[int]
    CLASSNAME_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    language: str
    serialization: str
    className: str
    data: bytes
    def __init__(self, language: _Optional[str] = ..., serialization: _Optional[str] = ..., className: _Optional[str] = ..., data: _Optional[bytes] = ...) -> None: ...
