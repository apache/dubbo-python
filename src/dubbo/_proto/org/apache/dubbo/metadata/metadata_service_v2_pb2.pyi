from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OpenAPIFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    JSON: _ClassVar[OpenAPIFormat]
    YAML: _ClassVar[OpenAPIFormat]
    PROTO: _ClassVar[OpenAPIFormat]
JSON: OpenAPIFormat
YAML: OpenAPIFormat
PROTO: OpenAPIFormat

class MetadataRequest(_message.Message):
    __slots__ = ("revision",)
    REVISION_FIELD_NUMBER: _ClassVar[int]
    revision: str
    def __init__(self, revision: _Optional[str] = ...) -> None: ...

class MetadataInfoV2(_message.Message):
    __slots__ = ("app", "version", "services")
    class ServicesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ServiceInfoV2
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ServiceInfoV2, _Mapping]] = ...) -> None: ...
    APP_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SERVICES_FIELD_NUMBER: _ClassVar[int]
    app: str
    version: str
    services: _containers.MessageMap[str, ServiceInfoV2]
    def __init__(self, app: _Optional[str] = ..., version: _Optional[str] = ..., services: _Optional[_Mapping[str, ServiceInfoV2]] = ...) -> None: ...

class ServiceInfoV2(_message.Message):
    __slots__ = ("name", "group", "version", "protocol", "port", "path", "params")
    class ParamsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    name: str
    group: str
    version: str
    protocol: str
    port: int
    path: str
    params: _containers.ScalarMap[str, str]
    def __init__(self, name: _Optional[str] = ..., group: _Optional[str] = ..., version: _Optional[str] = ..., protocol: _Optional[str] = ..., port: _Optional[int] = ..., path: _Optional[str] = ..., params: _Optional[_Mapping[str, str]] = ...) -> None: ...

class OpenAPIRequest(_message.Message):
    __slots__ = ("group", "version", "tag", "service", "openapi", "format", "pretty")
    GROUP_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    TAG_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    OPENAPI_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    PRETTY_FIELD_NUMBER: _ClassVar[int]
    group: str
    version: str
    tag: _containers.RepeatedScalarFieldContainer[str]
    service: _containers.RepeatedScalarFieldContainer[str]
    openapi: str
    format: OpenAPIFormat
    pretty: bool
    def __init__(self, group: _Optional[str] = ..., version: _Optional[str] = ..., tag: _Optional[_Iterable[str]] = ..., service: _Optional[_Iterable[str]] = ..., openapi: _Optional[str] = ..., format: _Optional[_Union[OpenAPIFormat, str]] = ..., pretty: _Optional[bool] = ...) -> None: ...

class OpenAPIInfo(_message.Message):
    __slots__ = ("definition",)
    DEFINITION_FIELD_NUMBER: _ClassVar[int]
    definition: str
    def __init__(self, definition: _Optional[str] = ...) -> None: ...
