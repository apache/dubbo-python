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
import ngh2
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream

from dubbo.transport.h2.aio import AioH2Client
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def _download(parameters):
    consumed, grown = anyio.Event(), anyio.Event()
    windows, pings = [], []
    body = b"x" * 800_000

    async def peer(stream):
        engine = ngh2.Connection(ngh2.Role.SERVER)
        engine.initiate_connection()
        async with stream:
            await stream.send(engine.data_to_send())
            reader = BufferedByteReceiveStream(stream)
            engine.receive_data(await reader.receive_exactly(24))
            while True:
                header = await reader.receive_exactly(9)
                payload = await reader.receive_exactly(int.from_bytes(header[:3], "big"))
                engine.receive_data(header + payload)
                for event in engine.events():
                    if isinstance(event, ngh2.RequestReceived):
                        engine.send_response(event.stream_id, ((b":status", b"200"),))
                        engine.send_data(event.stream_id, body, end_stream=True)
                    elif isinstance(event, ngh2.SettingsReceived):
                        window = event.settings.get(ngh2.Setting.INITIAL_WINDOW_SIZE)
                        if window is not None:
                            windows.append(window)
                            if window == 1605632:
                                grown.set()
                if header[3] == 6 and header[4] == 0:
                    pings.append(payload)
                    await consumed.wait()
                if outgoing := engine.data_to_send():
                    await stream.send(outgoing)

    async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener, anyio.create_task_group() as tasks:
        tasks.start_soon(listener.serve, peer)
        port = listener.extra(anyio.abc.SocketAttribute.local_port)
        async with AioH2Client(URL(protocol="tri", host="127.0.0.1", port=port, parameters=parameters)) as client:
            request = ((b":method", b"GET"), (b":scheme", b"http"), (b":authority", b"bdp"), (b":path", b"/"))
            async with await client.open_stream(request, end_stream=True) as stream:
                await stream.receive_headers()
                assert await stream.receive_data_exactly(len(body)) == body
            consumed.set()
            if not parameters:
                await grown.wait()
            async with await client.open_stream(request, end_stream=True) as stream:
                await stream.receive_headers()
                assert await stream.receive_data_exactly(len(body)) == body
            tasks.cancel_scope.cancel()

    return windows, pings


async def test_an_unset_stream_window_grows_by_settings_when_a_probe_asks():
    windows, pings = await _download({})

    assert windows == [1048576, 1605632]
    assert b"\xff" * 8 in pings


async def test_a_set_stream_window_is_fixed():
    windows, pings = await _download({"initial-window-size": "65535"})

    assert windows == [65535]
    assert pings == []
