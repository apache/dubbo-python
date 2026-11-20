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

import gzip

import anyio
import grpc
import pytest
from google.protobuf.wrappers_pb2 import StringValue

from dubbo import Status
from dubbo.protocol import Exporter
from dubbo.protocol.triple import TripleProtocol
from dubbo.protocol.triple.grpc.framing import frame
from dubbo.transport.h2 import H2Headers
from dubbo.transport.h2.aio import AioH2Client
from dubbo.url import URL

pytestmark = pytest.mark.anyio

# grpcio calls through threads of its own and keeps its deadlines on the real clock.
_grpcio = pytest.mark.real_clock


async def _raw(exporter: Exporter, headers: H2Headers, body: bytes | None = b"") -> dict[bytes, bytes]:
    url = URL(protocol="tri", host="127.0.0.1", port=exporter.url.port)
    async with AioH2Client(url) as client:
        stream = await client.open_stream(headers, end_stream=body is None)
        async with stream:
            if body is not None:
                await stream.send_data(body, end_stream=True)
            response = dict(await stream.receive_headers())
            trailers = await stream.receive_trailers() if b"grpc-status" not in response else None
            return response | dict(trailers or ())


def _request(path: bytes = b"/test.Echo/Say", **fields: bytes) -> H2Headers:
    headers = {
        b":method": b"POST",
        b":scheme": b"http",
        b":authority": b"localhost",
        b":path": path,
        b"content-type": b"application/grpc",
        b"te": b"trailers",
    }
    headers |= {name.replace("_", "-").encode(): value for name, value in fields.items()}
    return tuple(headers.items())


@pytest.mark.parametrize(
    ("headers", "body", "http_status", "status"),
    [
        # PROTOCOL-HTTP2.md:64
        (_request(content_type=b"application/json"), b"", b"415", Status.INVALID_ARGUMENT),
        # PROTOCOL-HTTP2.md:31-33
        (_request(grpc_timeout=b"1x"), b"", b"400", Status.INTERNAL),
        # PROTOCOL-HTTP2.md:25
        (_request(**{":method": b"PUT"}), b"", b"405", Status.INTERNAL),
        (_request(b"/test.Echo/Nope"), b"", b"200", Status.UNIMPLEMENTED),
        (_request(content_type=b"application/grpc+json"), b"", b"200", Status.INTERNAL),
        # compression.md:111-114
        (_request(grpc_encoding=b"snappy"), b"", b"200", Status.UNIMPLEMENTED),
        # compression.md:122-126
        (_request(), b"\x01\x00\x00\x00\x00", b"200", Status.INTERNAL),
        (_request(), (5 * 1024 * 1024).to_bytes(5, "big"), b"200", Status.RESOURCE_EXHAUSTED),
        # statuscodes.md:60
        (_request(), None, b"200", Status.UNIMPLEMENTED),
        (_request(), 2 * frame(StringValue(value="x").SerializeToString()), b"200", Status.UNIMPLEMENTED),
        (
            _request(b"/test.Echo/Count"),
            2 * frame(StringValue(value="1").SerializeToString()),
            b"200",
            Status.UNIMPLEMENTED,
        ),
        (_request(), b"\x00\x00\x00\x00\x02\xff\xff", b"200", Status.INTERNAL),
    ],
    ids=[
        "content-type",
        "timeout-unit",
        "method",
        "unknown-route",
        "serialization",
        "encoding",
        "missing-encoding",
        "message-limit",
        "missing-message",
        "extra-unary-message",
        "extra-server-stream-message",
        "malformed-protobuf",
    ],
)
async def test_the_server_rejects_broken_requests(
    protocol: TripleProtocol, impl, headers: H2Headers, body: bytes | None, http_status: bytes, status: Status, export
) -> None:
    exporter = await export(protocol, impl)

    response = await _raw(exporter, headers, body)

    assert response[b":status"] == http_status
    assert response[b"content-type"].startswith(b"application/grpc")
    assert response[b"grpc-status"] == b"%d" % status


@pytest.mark.parametrize("cut", [3, 7])
async def test_a_deadline_inside_a_request_message_ends_the_call_with_deadline_exceeded(
    protocol: TripleProtocol, impl, cut: int, export
) -> None:
    exporter = await export(protocol, impl)
    url = URL(protocol="tri", host="127.0.0.1", port=exporter.url.port)

    async with AioH2Client(url) as client, await client.open_stream(_request(grpc_timeout=b"50m")) as stream:
        await stream.send_data(frame(StringValue(value="hello").SerializeToString())[:cut])
        with anyio.fail_after(5):
            response = dict(await stream.receive_headers())

    assert response[b"grpc-status"] == b"%d" % Status.DEADLINE_EXCEEDED


async def test_an_unsupported_encoding_is_answered_with_the_supported_ones(
    protocol: TripleProtocol, impl, export
) -> None:
    exporter = await export(protocol, impl)

    response = await _raw(exporter, _request(grpc_encoding=b"snappy"))

    assert b"snappy" not in response[b"grpc-accept-encoding"]
    assert b"gzip" in response[b"grpc-accept-encoding"]


@_grpcio
async def test_a_rejected_call_reports_its_status_while_the_caller_still_sends(
    protocol: TripleProtocol, impl, export
) -> None:
    exporter = await export(protocol, impl)

    async with grpc.aio.insecure_channel(f"127.0.0.1:{exporter.url.port}") as channel:
        nope = channel.stream_stream("/test.Echo/Nope", request_serializer=StringValue.SerializeToString)
        call = nope()
        with pytest.raises(grpc.aio.AioRpcError) as raised:
            await call.read()

    assert raised.value.code() is grpc.StatusCode.UNIMPLEMENTED


async def test_the_server_reads_gzip_messages(protocol: TripleProtocol, impl, export) -> None:
    exporter = await export(protocol, impl)
    message = gzip.compress(StringValue(value="zipped").SerializeToString())

    response = await _raw(
        exporter, _request(grpc_encoding=b"gzip"), b"\x01" + len(message).to_bytes(4, "big") + message
    )

    assert response[b"grpc-status"] == b"0"
    # compression.md:38-42 leaves the response encoding to the server, which compresses only as configured.
    assert b"grpc-encoding" not in response
    # compression.md:53-56: a supported encoding the server has not disclosed is named in the response.
    assert b"gzip" in response[b"grpc-accept-encoding"]


@pytest.mark.parametrize(
    ("accept_encoding", "encoding"),
    [
        ({"grpc_accept_encoding": b"identity, gzip"}, b"gzip"),
        # compression.md:58-60
        ({"grpc_accept_encoding": b"identity"}, None),
        ({}, None),
    ],
)
async def test_a_compressing_server_compresses_for_callers_that_accept_it(
    protocol: TripleProtocol, impl, accept_encoding: dict[str, bytes], encoding: bytes | None, export
) -> None:
    exporter = await export(protocol, impl, "?triple.compressor=gzip")
    message = StringValue(value="plain").SerializeToString()

    response = await _raw(exporter, _request(**accept_encoding), b"\x00" + len(message).to_bytes(4, "big") + message)

    assert response[b"grpc-status"] == b"0"
    assert response.get(b"grpc-encoding") == encoding
