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

import grpc
import pytest
from google.protobuf.descriptor_pb2 import FileDescriptorProto

from dubbo import Status
from dubbo._proto.grpc.reflection.v1 import reflection_pb2 as v1
from dubbo._proto.grpc.reflection.v1alpha import reflection_pb2 as v1alpha

# grpcio calls through threads of its own and keeps its deadlines on the real clock.
pytestmark = [pytest.mark.anyio, pytest.mark.real_clock]


async def _reflect(exporter, request, version="v1alpha"):
    messages = v1 if version == "v1" else v1alpha
    async with grpc.aio.insecure_channel(f"127.0.0.1:{exporter.url.port}") as channel:
        info = channel.stream_stream(
            f"/grpc.reflection.{version}.ServerReflection/ServerReflectionInfo",
            request_serializer=messages.ServerReflectionRequest.SerializeToString,
            response_deserializer=messages.ServerReflectionResponse.FromString,
        )
        responses = [response async for response in info(iter([request]))]

    [response] = responses
    assert response.original_request == request
    return response


async def test_reflection_lists_exported_and_enabled_builtin_services(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true&triple.health-enabled=true")

    response = await _reflect(exporter, v1alpha.ServerReflectionRequest(host="h", list_services=""))

    assert response.valid_host == "h"
    assert [service.name for service in response.list_services_response.service] == [
        "grpc.health.v1.Health",
        "grpc.reflection.v1.ServerReflection",
        "grpc.reflection.v1alpha.ServerReflection",
        "test.Echo",
    ]


@pytest.mark.parametrize(
    ("query", "value", "files"),
    [
        ("file_containing_symbol", "grpc.health.v1.Health.Check", ["grpc/health/v1/health.proto"]),
        ("file_by_filename", "google/protobuf/wrappers.proto", ["google/protobuf/wrappers.proto"]),
        ("file_containing_symbol", "google.rpc.Status", ["google/rpc/status.proto", "google/protobuf/any.proto"]),
    ],
    ids=["method-symbol", "filename", "imported-dependency"],
)
async def test_reflection_returns_the_file_holding_the_queried_symbol_or_name_with_its_imports(
    query, value, files, protocol, impl, export
):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true&triple.health-enabled=true")

    response = await _reflect(exporter, v1alpha.ServerReflectionRequest(**{query: value}))

    descriptors = [
        FileDescriptorProto.FromString(data) for data in response.file_descriptor_response.file_descriptor_proto
    ]
    assert [descriptor.name for descriptor in descriptors] == files


async def test_reflection_returns_the_file_that_declares_a_method(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true&triple.health-enabled=true")

    request = v1alpha.ServerReflectionRequest(file_containing_symbol="grpc.health.v1.Health.Check")
    response = await _reflect(exporter, request)

    [data] = response.file_descriptor_response.file_descriptor_proto
    assert [service.name for service in FileDescriptorProto.FromString(data).service] == ["Health"]


async def test_reflection_v1_answers_as_v1alpha(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true")

    answer = await _reflect(exporter, v1.ServerReflectionRequest(file_containing_symbol="google.rpc.Status"), "v1")
    alpha = await _reflect(exporter, v1alpha.ServerReflectionRequest(file_containing_symbol="google.rpc.Status"))

    assert isinstance(answer, v1.ServerReflectionResponse)
    assert answer.file_descriptor_response.file_descriptor_proto == alpha.file_descriptor_response.file_descriptor_proto


@pytest.mark.parametrize(
    ("query", "code"),
    [
        (v1alpha.ServerReflectionRequest(file_containing_symbol="test.Nope"), Status.NOT_FOUND),
        (v1alpha.ServerReflectionRequest(file_containing_symbol="grpc.health.v1.Health.Nope"), Status.NOT_FOUND),
        (v1alpha.ServerReflectionRequest(), Status.INVALID_ARGUMENT),
    ],
    ids=["missing-symbol", "missing-method", "missing-query"],
)
async def test_reflection_returns_status_for_an_unknown_or_missing_query(query, code, protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true&triple.health-enabled=true")

    response = await _reflect(exporter, query)

    assert response.error_response.error_code == code


async def test_reflection_reports_no_extensions_for_a_type_without_them(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.reflection-enabled=true")

    response = await _reflect(
        exporter, v1alpha.ServerReflectionRequest(all_extension_numbers_of_type="google.protobuf.Any")
    )

    assert response.all_extension_numbers_response.base_type_name == "google.protobuf.Any"
    assert list(response.all_extension_numbers_response.extension_number) == []
