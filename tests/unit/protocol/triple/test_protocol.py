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

import ssl
import typing
from importlib import metadata

import pytest
from google.protobuf.wrappers_pb2 import StringValue

import dubbo
from dubbo.constants import DEFAULT_JAVA_SERIALIZATION
from dubbo.extension import extensions
from dubbo.protocol.triple import TripleProtocol
from dubbo.rpc.invocation import Invocation
from dubbo.serialization import Serialization
from dubbo.serialization.protobuf import ProtobufSerialization
from dubbo.url import SSL_CONTEXT

pytestmark = pytest.mark.anyio


@dubbo.service("test.Echo")
class _Echo(typing.Protocol):
    async def say(self, request: StringValue) -> StringValue: ...


async def test_a_reference_passes_transport_parameters_to_its_client(clients, client_url):
    url = client_url.update_parameters({"triple.stream-send-buffer-size": "1048576", "timeout": "1000"})

    async with TripleProtocol() as protocol:
        await protocol.refer(url, dubbo.get_definition(_Echo))

        assert [client.url.parameters for client in clients] == [
            {"client": "memory", "stream-send-buffer-size": "1048576"}
        ]

    assert all(client.closed for client in clients)


@pytest.mark.parametrize(("shared", "made"), [(False, ["a", "b"]), (True, ["a"])])
async def test_references_share_a_serialization_only_if_it_says_so(clients, client_url, shared, made) -> None:
    urls = []

    class Recording(ProtobufSerialization):
        def __init__(self, url):
            urls.append(url.parameters["setting"])

    Recording.shared = shared
    extensions.register(Serialization, "recording", Recording)
    url = client_url.update_parameters({"serialization": "recording"})

    async with TripleProtocol() as protocol:
        for setting in ("a", "b"):
            await protocol.refer(url.update_parameters({"setting": setting}), dubbo.get_definition(_Echo))

    assert urls == made


async def test_references_that_differ_only_in_call_settings_share_a_client(clients, client_url) -> None:
    call = {
        "interface": "demo.Greeter",
        "group": "g",
        "timeout": "100",
        "say.timeout": "50",
        "triple.compressor": "gzip",
    }

    async with TripleProtocol() as protocol:
        await protocol.refer(client_url, dubbo.get_definition(_Echo))
        await protocol.refer(client_url.update_parameters(call), dubbo.get_definition(_Echo))

    assert len(clients) == 1


@pytest.mark.parametrize(
    "parameters",
    [{"triple.max-concurrent-streams": "8"}, {"triple.stream-send-buffer-size": "1048576"}],
    ids=["max-concurrent-streams", "stream-send-buffer-size"],
)
async def test_references_of_other_connection_settings_get_another_client(
    clients, client_url, parameters: dict[str, str]
) -> None:
    async with TripleProtocol() as protocol:
        await protocol.refer(client_url, dubbo.get_definition(_Echo))
        await protocol.refer(client_url.update_parameters(parameters), dubbo.get_definition(_Echo))

    assert len(clients) == 2


async def test_references_of_different_tls_contexts_get_different_clients(clients, client_url) -> None:
    lax, strict = ssl.create_default_context(), ssl.create_default_context()

    async with TripleProtocol() as protocol:
        for context in (lax, lax, strict):
            await protocol.refer(client_url.replace(attributes={SSL_CONTEXT: context}), dubbo.get_definition(_Echo))

    assert len(clients) == 2


async def test_a_generic_call_without_its_plugin_tells_why_it_cannot_load(clients, client_url, monkeypatch):
    plugin = metadata.EntryPoint(
        name=DEFAULT_JAVA_SERIALIZATION, value="dubbo_absent:Plugin", group="apache_dubbo.serialization"
    )
    monkeypatch.setitem(extensions._entries(Serialization), DEFAULT_JAVA_SERIALIZATION, plugin)
    definition = dubbo.get_definition(_Echo)

    async with TripleProtocol() as protocol:
        invoker = await protocol.refer(client_url, definition)
        invocation = Invocation(
            interface="test.Echo", method="say", definition=definition.methods[0], arguments=("hi",), generic="true"
        )
        result = await invoker.invoke(invocation)

    assert result.error is not None
    assert "No module named 'dubbo_absent'" in str(result.error)
