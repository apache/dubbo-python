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

import anyio
import pytest

from dubbo.transport.h2.aio.connection import AioH2Connection
from dubbo.url import URL


class _RecordingTransport(asyncio.Transport):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[bytes] = []
        self.close_calls = 0

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.close_calls += 1

    def is_closing(self) -> bool:
        return self.close_calls > 0

    def get_write_buffer_size(self) -> int:
        return 0


class _RecordingTLSObject:
    def __init__(self, selected_alpn: str | None, version: str, compression: str | None) -> None:
        self._selected_alpn = selected_alpn
        self._version = version
        self._compression = compression

    def selected_alpn_protocol(self) -> str | None:
        return self._selected_alpn

    def version(self) -> str:
        return self._version

    def compression(self) -> str | None:
        return self._compression


class _RecordingTLSTransport(_RecordingTransport):
    def __init__(self, selected_alpn: str | None, version: str = "TLSv1.3", compression: str | None = None) -> None:
        super().__init__()
        self._ssl_object = _RecordingTLSObject(selected_alpn, version, compression)
        self.abort_calls = 0

    def get_extra_info(self, name: str, default=None):
        if name == "ssl_object":
            return self._ssl_object
        return default

    def abort(self) -> None:
        self.abort_calls += 1


def _connection_url(
    *,
    max_concurrent_streams: int | None = None,
    keep_alive_interval: float | None = None,
    keep_alive_timeout: float | None = None,
) -> URL:
    """Return a URL that sets the given HTTP/2 options of a connection, with times in seconds."""
    parameters = {
        "max-concurrent-streams": None if max_concurrent_streams is None else str(max_concurrent_streams),
        "keep-alive-interval": None if keep_alive_interval is None else str(round(keep_alive_interval * 1000)),
        "keep-alive-timeout": None if keep_alive_timeout is None else str(round(keep_alive_timeout * 1000)),
    }
    return URL(
        protocol="tri",
        host="127.0.0.1",
        port=1,
        parameters={key: value for key, value in parameters.items() if value is not None},
    )


@pytest.fixture
def connection_url():
    return _connection_url


@pytest.fixture
def transport_type():
    return _RecordingTransport


@pytest.fixture
def tls_transport_type():
    return _RecordingTLSTransport


class _Timer:
    def __init__(self, deadline, callback):
        self.deadline = deadline
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _Clock:
    def __init__(self):
        self.now = 100.0
        self.timers = []

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def call_at(self, deadline, callback):
        timer = _Timer(deadline, callback)
        self.timers.append(timer)
        return timer

    def call_later(self, delay, callback):
        return self.call_at(self.now + delay, callback)

    def advance(self, seconds):
        target = self.now + seconds
        while active := [timer for timer in self.timers if not timer.cancelled and timer.deadline <= target]:
            timer = min(active, key=lambda timer: timer.deadline)
            self.timers.remove(timer)
            self.now = timer.deadline
            timer.callback()
        self.now = target


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def keep_alive_clock(monkeypatch, clock):
    from dubbo.transport.h2.aio.keep_alive import KeepAlive

    monkeypatch.setattr(
        "dubbo.transport.h2.aio.connection.KeepAlive", lambda loop, **options: KeepAlive(clock, **options)
    )
    return clock


@pytest.fixture
async def h2_pair(credits):
    import ngh2

    class CreditingConnection(AioH2Connection):
        def consume(self, stream_id, amount):
            if amount:
                credits.append((stream_id, amount))
            super().consume(stream_id, amount)

    client = CreditingConnection(ngh2.Role.CLIENT, url=_connection_url())
    streams = []
    server = AioH2Connection(ngh2.Role.SERVER, url=_connection_url(), on_stream=streams.append)
    client_wire, server_wire = _RecordingTransport(), _RecordingTransport()
    client.connection_made(client_wire)
    server.connection_made(server_wire)

    async def exchange():
        await anyio.wait_all_tasks_blocked()
        while client_wire.writes or server_wire.writes:
            for wire, receiver in [(client_wire, server), (server_wire, client)]:
                data = b"".join(wire.writes)
                wire.writes.clear()
                for start in range(0, len(data), 65536):
                    chunk = data[start : start + 65536]
                    receiver.get_buffer(len(chunk))[: len(chunk)] = chunk
                    receiver.buffer_updated(len(chunk))
            await anyio.wait_all_tasks_blocked()

    yield client, server, streams, exchange

    client.connection_lost(None)
    server.connection_lost(None)


@pytest.fixture
def credits():
    return []
