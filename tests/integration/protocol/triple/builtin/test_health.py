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

import anyio
import grpc
import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo import RpcError, Status
from dubbo._proto.grpc.health.v1.health_pb2 import HealthCheckRequest, HealthCheckResponse, HealthListRequest
from dubbo.protocol.triple import TripleProtocol
from dubbo.protocol.triple.builtin.health import Health
from dubbo.rpc.client import proxy
from dubbo.url import URL

pytestmark = pytest.mark.anyio

# grpcio calls through threads of its own and keeps its deadlines on the real clock.
_grpcio = pytest.mark.real_clock

_HEALTH = "grpc.health.v1.Health"


async def test_the_health_service_is_off_by_default(protocol: TripleProtocol, impl, export) -> None:
    exporter = await export(protocol, impl)
    health = proxy(
        Health,
        (
            await protocol.refer(
                URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}"), dubbo.get_definition(Health)
            )
        ).invoke,
    )

    with pytest.raises(RpcError) as raised:
        await health.check(HealthCheckRequest())
    assert raised.value.status is Status.UNIMPLEMENTED


@pytest.mark.parametrize("name", ["", "test.Echo", "g/test.Echo:1"], ids=["server", "interface", "service-key"])
async def test_health_check_reports_an_exported_service_as_serving(name, protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.health-enabled=true&group=g&version=1")
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}")
    health = proxy(Health, (await protocol.refer(url, dubbo.get_definition(Health))).invoke)

    response = await health.check(HealthCheckRequest(service=name))

    assert response.status == HealthCheckResponse.SERVING


async def test_health_check_of_an_unknown_service_is_not_found(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.health-enabled=true&group=g&version=1")
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}")
    health = proxy(Health, (await protocol.refer(url, dubbo.get_definition(Health))).invoke)

    with pytest.raises(RpcError, match="NOT_FOUND") as raised:
        await health.check(HealthCheckRequest(service="test.Nope"))

    assert raised.value.status is Status.NOT_FOUND


async def test_health_list_contains_the_server_interface_and_service_key(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.health-enabled=true&group=g&version=1")
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}")
    health = proxy(Health, (await protocol.refer(url, dubbo.get_definition(Health))).invoke)

    statuses = (await health.list(HealthListRequest())).statuses

    assert {name: response.status for name, response in statuses.items()} == {
        "": HealthCheckResponse.SERVING,
        "test.Echo": HealthCheckResponse.SERVING,
        "g/test.Echo:1": HealthCheckResponse.SERVING,
    }


async def test_health_watch_reports_unexported_service_without_stopping_the_server(protocol, impl, export):
    exporter = await export(protocol, impl, "?triple.health-enabled=true&group=g&version=1")
    url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}")
    health = proxy(Health, (await protocol.refer(url, dubbo.get_definition(Health))).invoke)

    async with health.watch(HealthCheckRequest(service="test.Echo")) as watch:
        assert (await watch.receive()).status == HealthCheckResponse.SERVING
        await exporter.aclose()
        assert (await watch.receive()).status == HealthCheckResponse.NOT_SERVING

    assert (await health.check(HealthCheckRequest(service=""))).status == HealthCheckResponse.SERVING


async def test_closing_the_server_ends_health_watches(impl, export) -> None:
    async with TripleProtocol() as serving:
        exporter = await export(serving, impl, "?triple.health-enabled=true")
        url = URL.parse(f"tri://127.0.0.1:{exporter.url.port}/{_HEALTH}")
        async with TripleProtocol() as calling:
            health = proxy(Health, (await calling.refer(url, dubbo.get_definition(Health))).invoke)
            with anyio.fail_after(5):
                async with health.watch(HealthCheckRequest(service="")) as watch:
                    assert (await watch.receive()).status == HealthCheckResponse.SERVING
                    await serving.aclose()
                    assert [response.status async for response in watch] == [HealthCheckResponse.NOT_SERVING]


async def test_announcing_the_shutdown_reports_not_serving_while_the_services_serve(
    impl, export, serve, refer, echo_impl_type
) -> None:
    async with TripleProtocol() as serving:
        exporter = await export(serving, impl, "?triple.health-enabled=true")
        port = exporter.url.port
        async with TripleProtocol() as calling:
            health = proxy(
                Health,
                (
                    await calling.refer(URL.parse(f"tri://127.0.0.1:{port}/{_HEALTH}"), dubbo.get_definition(Health))
                ).invoke,
            )
            echo = await refer(calling, exporter)
            with anyio.fail_after(5):
                async with health.watch(HealthCheckRequest(service="")) as watch:
                    assert (await watch.receive()).status == HealthCheckResponse.SERVING
                    serving.announce_shutdown()
                    assert (await watch.receive()).status == HealthCheckResponse.NOT_SERVING

                    url = URL.parse(f"tri://127.0.0.1:{port}/test.Echo?version=2&triple.health-enabled=true")
                    await serve(serving, url, echo_impl_type())
                    for name in ("", "test.Echo"):
                        status = (await health.check(HealthCheckRequest(service=name))).status
                        assert status == HealthCheckResponse.NOT_SERVING
                    assert [await echo.say(StringValue(value=str(i))) for i in range(3)] == [
                        StringValue(value=f"{i}|-") for i in range(3)
                    ]


@_grpcio
async def test_a_grpcio_client_checks_health(protocol: TripleProtocol, impl, export) -> None:
    exporter = await export(protocol, impl, "?triple.health-enabled=true")

    async with grpc.aio.insecure_channel(f"127.0.0.1:{exporter.url.port}") as channel:
        check = channel.unary_unary(
            f"/{_HEALTH}/Check",
            request_serializer=HealthCheckRequest.SerializeToString,
            response_deserializer=HealthCheckResponse.FromString,
        )
        response = await check(HealthCheckRequest(service="test.Echo"))

    assert response.status == HealthCheckResponse.SERVING
