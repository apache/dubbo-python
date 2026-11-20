# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""The gRPC reflection services, grpc.reflection.v1.ServerReflection and its earlier grpc.reflection.v1alpha."""

from collections.abc import Callable, Iterable
from typing import Any, ClassVar, TypeVar

from google.protobuf import descriptor_pool
from google.protobuf.descriptor import FileDescriptor

from dubbo._proto.grpc.reflection.v1 import reflection_dubbo as v1_dubbo
from dubbo._proto.grpc.reflection.v1 import reflection_pb2 as v1_pb2
from dubbo._proto.grpc.reflection.v1alpha import reflection_dubbo as v1alpha_dubbo
from dubbo._proto.grpc.reflection.v1alpha import reflection_pb2 as v1alpha_pb2
from dubbo._proto.pool import pool
from dubbo.exceptions import Status
from dubbo.rpc.stream import Stream

__all__ = ["ReflectionService", "ReflectionV1AlphaService"]

T = TypeVar("T")


class _Reflection:
    """Describes the services of a server and the protobuf files that define them.

    Files are looked up among the framework's own protos, then in protobuf's
    default pool, where generated modules register theirs.

    Args:
        services: Returns the interfaces the server serves.
    """

    # The response message of the version served; the requests of both versions have the same fields.
    _response: ClassVar[type[Any]]

    def __init__(self, services: Callable[[], Iterable[str]]) -> None:
        self._services = services
        self._pools = (pool, descriptor_pool.Default())

    async def server_reflection_info(self, stream: Stream[Any, Any]) -> None:
        async for request in stream:
            await stream.send(self._respond(request))

    def _respond(self, request: Any) -> Any:
        response = self._response(valid_host=request.host, original_request=request)

        try:
            match request.WhichOneof("message_request"):
                case "list_services":
                    services = response.list_services_response.service
                    for name in sorted(self._services()):
                        services.add(name=name)
                case "file_by_filename":
                    file = self._find(lambda p: p.FindFileByName(request.file_by_filename))
                    response.file_descriptor_response.file_descriptor_proto.extend(_with_dependencies(file))
                case "file_containing_symbol":
                    file = self._find(lambda p: _symbol_file(p, request.file_containing_symbol))
                    response.file_descriptor_response.file_descriptor_proto.extend(_with_dependencies(file))
                case "file_containing_extension":
                    extension = request.file_containing_extension
                    file = self._find(
                        lambda p: _extension_file(p, extension.containing_type, extension.extension_number)
                    )
                    response.file_descriptor_response.file_descriptor_proto.extend(_with_dependencies(file))
                case "all_extension_numbers_of_type":
                    name = request.all_extension_numbers_of_type
                    numbers = self._find(lambda p: _extension_numbers(p, name))
                    response.all_extension_numbers_response.base_type_name = name
                    response.all_extension_numbers_response.extension_number.extend(sorted(numbers))
                case _:
                    response.error_response.error_code = Status.INVALID_ARGUMENT
                    response.error_response.error_message = "the request asks for nothing"
        except KeyError as error:
            response.error_response.error_code = Status.NOT_FOUND
            response.error_response.error_message = str(error.args[0] if error.args else error)

        return response

    def _find(self, lookup: Callable[[descriptor_pool.DescriptorPool], T]) -> T:
        """Return what ``lookup`` finds in the first pool that has it.

        Raises:
            KeyError: No pool has it.
        """
        for each in self._pools[:-1]:
            try:
                return lookup(each)
            except KeyError:
                pass

        return lookup(self._pools[-1])


class ReflectionService(_Reflection, v1_dubbo.ServerReflectionServicer):
    """Serves grpc.reflection.v1.ServerReflection."""

    _response = v1_pb2.ServerReflectionResponse


class ReflectionV1AlphaService(_Reflection, v1alpha_dubbo.ServerReflectionServicer):
    """Serves grpc.reflection.v1alpha.ServerReflection, for clients that do not know v1."""

    _response = v1alpha_pb2.ServerReflectionResponse


def _symbol_file(pool: descriptor_pool.DescriptorPool, symbol: str) -> FileDescriptor:
    try:
        return pool.FindFileContainingSymbol(symbol)
    except KeyError:
        # The pool finds no methods by name; a method is found through its service.
        name, _, method = symbol.rpartition(".")
        try:
            service = pool.FindServiceByName(name)
        except KeyError:
            pass
        else:
            if method in service.methods_by_name:
                return service.file
        raise


def _extension_file(pool: descriptor_pool.DescriptorPool, containing_type: str, number: int) -> FileDescriptor:
    message = pool.FindMessageTypeByName(containing_type)
    found = pool.FindExtensionByNumber(message, number)
    return pool.FindFileContainingSymbol(found.full_name)


def _extension_numbers(pool: descriptor_pool.DescriptorPool, name: str) -> list[int]:
    message = pool.FindMessageTypeByName(name)
    return [extension.number for extension in pool.FindAllExtensions(message)]


def _with_dependencies(file: FileDescriptor) -> list[bytes]:
    """Return ``file`` and every file it imports, directly or not, as serialized FileDescriptorProtos."""
    found: dict[str, bytes] = {}
    pending = [file]
    while pending:
        current = pending.pop()
        if current.name not in found:
            found[current.name] = current.serialized_pb
            pending.extend(current.dependencies)

    return list(found.values())
