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

import asyncio
from functools import partial

import anyio
import ngh2
import pytest

import dubbo.utils.async_ as async_module
from dubbo.transport.h2 import (
    H2ConnectionError,
    H2StreamError,
)
from dubbo.transport.h2.aio.connection import AioH2Connection

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("peername", "peer"),
    [(("127.0.0.1", 5000), "127.0.0.1:5000"), (("::1", 5000, 0, 0), "[::1]:5000"), ("/tmp/socket", None), (None, None)],
    ids=["ipv4", "ipv6", "unix", "absent"],
)
async def test_stream_peer_formats_the_transport_address(
    peername, peer, connection_url, transport_type, request_headers
):
    class PeerTransport(transport_type):
        def get_extra_info(self, name, default=None):
            return peername if name == "peername" else default

    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(PeerTransport())
    stream = await connection.open_stream(request_headers, end_stream=True)

    assert stream.peer == peer
    connection.connection_lost(None)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_connection_rejects_a_send_buffer_that_is_not_positive(value: str, h2_url) -> None:
    with pytest.raises(ValueError, match="stream-send-buffer-size"):
        AioH2Connection(ngh2.Role.CLIENT, url=h2_url("127.0.0.1", 1, stream_send_buffer_size=value))


@pytest.mark.parametrize(
    ("transport", "message"),
    [
        ((None, "TLSv1.3", None), "ALPN"),
        (("h2", "TLSv1.1", None), "TLSv1.1"),
        (("h2", "TLSv1.3", "zlib"), "compression"),
    ],
)
async def test_tls_connection_requires_what_http2_needs_before_sending_preface(
    transport: tuple[str | None, str, str | None], message: str, connection_url, tls_transport_type
) -> None:
    connection = AioH2Connection(
        ngh2.Role.CLIENT,
        url=connection_url(),
        require_h2_alpn=True,
    )

    transport = tls_transport_type(*transport)
    connection.connection_made(transport)

    assert transport.abort_calls == 1
    assert not transport.writes
    connection.start_close()
    assert not transport.writes
    with pytest.raises(H2ConnectionError, match=message):
        connection.raise_if_failed()
    connection.connection_lost(None)


async def test_keep_alive_deadline_survives_backpressure_and_ignores_an_unmatched_ack(
    connection_url, transport_type, keep_alive_clock
):
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url(keep_alive_interval=10, keep_alive_timeout=20))
    transport = transport_type()
    connection.connection_made(transport)
    server = ngh2.Connection(ngh2.Role.SERVER)
    server.initiate_connection()

    def receive(data):
        connection.get_buffer(len(data))[: len(data)] = data
        connection.buffer_updated(len(data))

    receive(server.data_to_send())
    connection.pause_writing()
    keep_alive_clock.advance(10)
    connection.resume_writing()
    assert b"".join(transport.writes).endswith(b"\x00\x00\x08\x06\x00\x00\x00\x00\x00" + (1).to_bytes(8, "big"))
    receive(b"\x00\x00\x08\x06\x01\x00\x00\x00\x00" + b"87654321")
    keep_alive_clock.advance(19)
    connection.raise_if_failed()

    receive(b"\x00\x00\x08\x06\x01\x00\x00\x00\x00" + (1).to_bytes(8, "big"))
    keep_alive_clock.advance(1)
    connection.raise_if_failed()
    connection.connection_lost(None)
    keep_alive_clock.advance(100)


async def test_inbound_bytes_postpone_keep_alive_without_engine_events(
    connection_url, transport_type, keep_alive_clock
):
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url(keep_alive_interval=10))
    transport = transport_type()
    connection.connection_made(transport)
    preface = b"".join(transport.writes)
    keep_alive_clock.advance(5)

    connection.get_buffer(1)[0] = 0
    connection.buffer_updated(1)
    keep_alive_clock.advance(5)
    await anyio.wait_all_tasks_blocked()
    assert b"".join(transport.writes) == preface

    keep_alive_clock.advance(5)
    await anyio.wait_all_tasks_blocked()
    assert b"".join(transport.writes) == preface + b"\x00\x00\x08\x06\x00\x00\x00\x00\x00" + (1).to_bytes(8, "big")
    connection.connection_lost(None)


async def test_keep_alive_timeout_fails_streams_and_aborts_connection(
    connection_url, transport_type, keep_alive_clock, request_headers
):
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url(keep_alive_interval=10, keep_alive_timeout=20))

    class AbortTransport(transport_type):
        aborts = 0

        def abort(self):
            self.aborts += 1
            connection.connection_lost(None)

    transport = AbortTransport()
    connection.connection_made(transport)
    stream = await connection.open_stream(request_headers, end_stream=True)
    connection.pause_writing()

    keep_alive_clock.advance(30)

    assert transport.aborts == 1
    assert connection.closed
    with pytest.raises(H2ConnectionError, match="PING acknowledgement timed out"):
        await stream.receive_headers()


async def test_pre_attachment_close_finishes_once_after_transport_loss(connection_url, transport_type) -> None:
    closed: list[AioH2Connection] = []
    connection = AioH2Connection(
        ngh2.Role.CLIENT,
        url=connection_url(),
        on_closed=closed.append,
    )

    connection.start_close()
    assert not connection.closed
    assert not closed

    transport = transport_type()
    connection.connection_made(transport)
    assert transport.close_calls == 1
    assert not connection.closed

    connection.connection_lost(None)
    await connection.wait_closed()
    assert connection.closed
    assert closed == [connection]

    connection.connection_lost(None)
    assert closed == [connection]


async def test_connection_aclose_waits_for_connection_lost_after_abort(
    monkeypatch: pytest.MonkeyPatch, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    loop = asyncio.get_running_loop()

    class AbortTransport(transport_type):
        def __init__(self) -> None:
            super().__init__()
            self.abort_calls = 0

        def abort(self) -> None:
            self.abort_calls += 1
            loop.call_soon(connection.connection_lost, None)

    transport = AbortTransport()
    connection.connection_made(transport)
    monkeypatch.setattr(async_module, "_CLOSE_GRACE", 0.0)

    await connection.aclose()

    assert transport.abort_calls == 1
    assert connection.closed


async def test_stream_reports_a_failure_found_while_writing_its_headers(
    request_headers, connection_url, transport_type
) -> None:
    class _BusyTransport(transport_type):
        def get_write_buffer_size(self) -> int:
            return 1

    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(_BusyTransport())
    headers = (*request_headers, (b"x-large", b"x" * 70_000))

    # The engine finds the oversized field only when it writes the frame, at the end of the iteration.
    stream = await connection.open_stream(headers, end_stream=True)

    with pytest.raises(H2StreamError):
        await stream.receive_headers()


async def test_an_idle_client_reports_invalid_headers_when_opening_beside_another_call(
    request_headers, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(transport_type())
    await connection.open_stream(request_headers, end_stream=False)

    with pytest.raises(H2StreamError):
        await connection.open_stream((*request_headers, (b"x-large", b"x" * 70_000)), end_stream=True)


async def test_cancelled_open_withdraws_the_stream_before_its_headers_leave(
    request_headers, connection_url, transport_type
) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    transport = transport_type()
    connection.connection_made(transport)
    preface = b"".join(transport.writes)
    connection.pause_writing()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(partial(connection.open_stream, request_headers, end_stream=True))
        # The stream exists and its open waits for asyncio to resume writing.
        await anyio.wait_all_tasks_blocked()
        task_group.cancel_scope.cancel()

    connection.resume_writing()

    # The reset stream's HEADERS never leave, so nothing follows the preface.
    assert b"".join(transport.writes) == preface
    # Nothing public shows that the connection let go of the stream.
    assert not connection._streams_by_id


async def test_a_lost_connection_forgets_its_streams(request_headers, connection_url, transport_type) -> None:
    connection = AioH2Connection(ngh2.Role.CLIENT, url=connection_url())
    connection.connection_made(transport_type())
    stream = await connection.open_stream(request_headers, end_stream=True)

    connection.connection_lost(None)

    # A stream the caller still holds keeps no sibling, and reports the loss.
    assert not connection._streams_by_id
    with pytest.raises(H2ConnectionError):
        await stream.receive_headers()
