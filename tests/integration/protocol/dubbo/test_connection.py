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
import socket
import struct

import anyio
import hessian2
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream

import dubbo
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.url import URL

pytestmark = pytest.mark.anyio


async def test_bytes_that_are_not_dubbo_close_the_connection(protocol: DubboProtocol, impl, export) -> None:
    exporter = await export(protocol, impl)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(b"ls\r\n" + b"\x00" * 16)
        sock.setblocking(False)
        assert await asyncio.get_running_loop().sock_recv(sock, 1) == b""


async def test_heartbeats_keep_an_idle_connection_open(protocol, user_service, find_invocation, frame):
    heartbeats = anyio.Event()
    accepted = []
    count = 0

    async def answer(stream):
        nonlocal count
        accepted.append(stream)
        async with stream:
            reader = BufferedByteReceiveStream(stream)
            while True:
                header = await reader.receive_exactly(16)
                _, flags, _, request_id, length = struct.unpack(">HBBqI", header)
                body = await reader.receive_exactly(length)
                if flags & 0x20:
                    assert hessian2.loads(body) is None
                    await stream.send(frame(0x22, request_id, b"N", status=20))
                    count += 1
                    if count == 5:
                        heartbeats.set()
                else:
                    response = hessian2.dumps_many([2])
                    await stream.send(frame(2, request_id, response, status=20))

    async with await anyio.create_tcp_listener(local_host="127.0.0.1") as listener, anyio.create_task_group() as tasks:
        tasks.start_soon(listener.serve, answer)
        port = listener.extra(anyio.abc.SocketAttribute.local_port)
        url = URL.parse(f"dubbo://127.0.0.1:{port}/com.example.UserService?heartbeat=50&heartbeat.timeout=250")
        invoker = await protocol.refer(url, dubbo.get_definition(user_service))
        find = find_invocation(arguments=("nobody", 1))
        assert (await invoker.invoke(find)).error is None

        await heartbeats.wait()

        assert (await invoker.invoke(find)).error is None
        assert len(accepted) == 1
        tasks.cancel_scope.cancel()


async def test_heartbeats_keep_a_connection_to_the_server_open(protocol: DubboProtocol, impl, export, frame) -> None:
    exporter = await export(protocol, impl, "?heartbeat=50&heartbeat.timeout=250")

    async with await anyio.connect_tcp("127.0.0.1", exporter.url.port) as stream:
        reader = BufferedByteReceiveStream(stream)
        # A heartbeat each 50 ms, past three times the idle timeout, so that the server would have closed a silent
        # connection.
        for request_id in range(1, 16):
            await stream.send(frame(0xE2, request_id, b"N"))
            header = await reader.receive_exactly(16)
            assert struct.unpack(">HBBqI", header) == (0xDABB, 0x22, 20, request_id, 1)
            assert await reader.receive_exactly(1) == b"N"
            await anyio.sleep(0.05)


async def test_the_server_acknowledges_a_heartbeat_without_invoking_a_service(protocol, impl, export, frame):
    exporter = await export(protocol, impl)

    async with await anyio.connect_tcp("127.0.0.1", exporter.url.port) as stream:
        await stream.send(frame(0xE2, 42, b"N"))
        reader = BufferedByteReceiveStream(stream)
        header = await reader.receive_exactly(16)
        body = await reader.receive_exactly(1)

    assert struct.unpack(">HBBqI", header) == (0xDABB, 0x22, 20, 42, 1)
    assert body == b"N"


async def test_a_silent_connection_is_closed(protocol: DubboProtocol, impl, export) -> None:
    exporter = await export(protocol, impl, "?heartbeat=20&heartbeat.timeout=60")

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.setblocking(False)
        with anyio.fail_after(2):
            assert await asyncio.get_running_loop().sock_recv(sock, 1) == b""
