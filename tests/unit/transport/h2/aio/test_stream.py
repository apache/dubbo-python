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

from functools import partial

import anyio
import ngh2
import pytest

from dubbo.transport.h2 import (
    H2ErrorCode,
    H2StreamError,
    H2StreamResetError,
)
from dubbo.transport.h2.aio import AioH2Stream
from dubbo.transport.h2.aio.connection import AioH2Connection

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("parameters", "size", "returns"),
    [({}, 256 * 1024, True), ({}, 512 * 1024, False), ({"stream_send_buffer_size": "1048576"}, 512 * 1024, True)],
    ids=["default-fits", "default-full", "configured-fits"],
)
async def test_send_blocks_only_when_queued_body_exceeds_the_send_buffer(
    parameters, size, returns, h2_url, transport_type, request_headers
):
    connection = AioH2Connection(ngh2.Role.CLIENT, url=h2_url("127.0.0.1", 1, **parameters))
    connection.connection_made(transport_type())
    stream = await connection.open_stream(request_headers, end_stream=False)
    returned = anyio.Event()

    async def send():
        await stream.send_data(b"x" * size)
        returned.set()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(send)
        await anyio.wait_all_tasks_blocked()
        assert returned.is_set() is returns
        tasks.cancel_scope.cancel()

    connection.connection_lost(None)


async def test_send_rejects_overlap_and_waits_for_asyncio_backpressure(
    request_headers, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    transport = transport_type()
    connection.connection_made(transport)
    stream = await connection.open_stream(request_headers, end_stream=False)
    assert stream is not None

    connection.pause_writing()
    writes_before_send = len(transport.writes)
    completed = anyio.Event()

    async def send() -> None:
        await stream.send_data(b"payload", end_stream=True)
        completed.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(send)
        await anyio.wait_all_tasks_blocked()
        assert not completed.is_set()
        assert len(transport.writes) == writes_before_send
        with pytest.raises(H2StreamError, match="already sending"):
            await stream.send_data(b"overlap")
        connection.resume_writing()
        await completed.wait()


async def test_end_remains_idempotent_after_the_send_direction_has_ended(
    request_headers, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(transport_type())
    stream = await connection.open_stream(request_headers, end_stream=True)
    assert stream is not None

    connection.connection_lost(None)

    await stream.end()


@pytest.mark.parametrize("operation", ["headers", "data", "trailers", "end"])
async def test_cancelling_a_queued_send_resets_the_stream_for_both_peers(
    operation, h2_pair, request_headers, response_headers
):
    client, server, streams, exchange = h2_pair
    peer = await client.open_stream(request_headers, end_stream=False)
    await exchange()
    stream = streams[0]
    if operation != "headers":
        await stream.send_headers(response_headers)
        await exchange()
    server.pause_writing()
    scopes = []

    async def send():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            if operation == "headers":
                await stream.send_headers(response_headers, end_stream=True)
            elif operation == "data":
                await stream.send_data(b"payload", end_stream=True)
            elif operation == "trailers":
                await stream.send_trailers(((b"grpc-status", b"0"),))
            else:
                await stream.end()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(send)
        await anyio.wait_all_tasks_blocked()
        scopes[0].cancel()

    with pytest.raises(H2StreamError, match="reset locally"):
        await stream.receive_data()
    server.resume_writing()
    await exchange()
    with pytest.raises(H2StreamResetError, match="reset") as raised:
        await peer.receive_data()
    assert raised.value.error_code == H2ErrorCode.CANCEL


async def test_cancelled_send_wakes_receiver_when_reset_fails(request_headers, connection_url, transport_type) -> None:
    class FailingResetConnection(AioH2Connection):
        def reset_stream(self, stream_id, error_code):
            raise H2StreamError("reset failed", stream_id=stream_id)

    connection = FailingResetConnection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(transport_type())
    stream = await connection.open_stream(request_headers, end_stream=False)
    assert stream is not None
    connection.pause_writing()

    async def receive() -> None:
        with pytest.raises(H2StreamError, match="operation was cancelled"):
            await stream.receive_headers()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(receive)
        async with anyio.create_task_group() as sending:
            sending.start_soon(partial(stream.send_data, b"payload", end_stream=True))
            await anyio.wait_all_tasks_blocked()
            sending.cancel_scope.cancel()


async def test_receive_rejects_overlap_and_reset_wakes_a_waiter(
    request_headers, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(transport_type())
    stream = await connection.open_stream(request_headers, end_stream=True)
    assert stream is not None
    completed = anyio.Event()

    async def receive() -> None:
        with pytest.raises(H2StreamError, match="reset locally"):
            await stream.receive_headers()
        completed.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(receive)
        await anyio.wait_all_tasks_blocked()
        connection.pause_writing()
        with pytest.raises(H2StreamError, match="already receiving"):
            await stream.receive_data_exactly(0)
        await stream.reset()
        with anyio.fail_after(5):
            await completed.wait()

    connection.resume_writing()


async def test_cancelling_exact_receive_preserves_partial_bytes_for_the_next_receive(
    h2_pair, request_headers, response_headers, credits
):
    client, _server, streams, exchange = h2_pair
    stream = await client.open_stream(request_headers, end_stream=True)
    await exchange()
    peer = streams[0]
    await peer.send_headers(response_headers)
    await peer.send_data(b"abc")
    await exchange()
    scopes = []

    async def receive():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await stream.receive_data_exactly(5)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(receive)
        await anyio.wait_all_tasks_blocked()
        scopes[0].cancel()

    assert credits == [(stream.stream_id, 3)]

    await peer.send_data(b"defg", end_stream=True)
    await exchange()

    assert await stream.receive_data_exactly(5) == b"abcde"
    assert await stream.receive_data_exactly(2) == b"fg"
    assert credits == [(stream.stream_id, 3), (stream.stream_id, 2), (stream.stream_id, 2)]
    assert await stream.receive_data() == b""


@pytest.mark.parametrize("error_code", [-1, 0x1_0000_0000])
async def test_reset_validates_error_code_after_stream_finished(error_code: int, connection_url) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    stream = AioH2Stream(connection, 1, headers_sent=True)
    stream._on_closed()

    with pytest.raises(ValueError, match="unsigned 32-bit"):
        await stream.reset(error_code)
