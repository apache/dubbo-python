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
import importlib.util
import json
import socket
import struct
import sys
from pathlib import Path
from typing import Any

import anyio
import hessian2
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream

import dubbo
from dubbo import RpcError, Status
from dubbo.exceptions import RemoteError
from dubbo.protocol.dubbo import DubboProtocol
from dubbo.rpc import Invocation, Result
from dubbo.rpc.client import proxy
from dubbo.rpc.server import ServiceInvoker
from dubbo.url import URL

pytestmark = pytest.mark.anyio


def _request_body(method: str, descriptor: str, *arguments: Any) -> bytes:
    values = ("2.0.2", "com.example.UserService", "0.0.0", method, descriptor, *arguments, {})
    return hessian2.dumps_many(values)


async def _receive(sock: socket.socket, size: int) -> bytes:
    """Return the next ``size`` bytes from the non-blocking ``sock``, or fewer if the peer closes it first."""
    received = b""
    while len(received) < size and (chunk := await asyncio.get_running_loop().sock_recv(sock, size - len(received))):
        received += chunk
    return received


async def _response(sock: socket.socket) -> tuple[int, int, int, bytes]:
    _, flags, status, request_id, length = struct.unpack(">HBBqI", await _receive(sock, 16))
    return flags, status, request_id, await _receive(sock, length)


class _Broken(ServiceInvoker):
    async def invoke(self, invocation: Invocation):
        raise RuntimeError("broken")


async def test_an_invoker_that_raises_answers_service_error_and_is_logged(
    protocol: DubboProtocol, impl, refer, user_service, caplog
) -> None:
    url = URL.parse("dubbo://127.0.0.1:0/com.example.UserService")
    exporter = await protocol.export(url, dubbo.get_definition(user_service), _Broken.from_implementation(impl, url))
    users = await refer(protocol, exporter)

    with pytest.raises(RpcError, match=r"^INTERNAL: SERVICE_ERROR: RuntimeError: broken$"):
        await users.find("alice", hessian2.Long(1))

    [record] = [record for record in caplog.records if "raised instead of returning a result" in record.getMessage()]
    assert (record.levelname, str(record.exc_info[1])) == ("ERROR", "broken")


class _Refusing(ServiceInvoker):
    async def invoke(self, invocation: Invocation):
        return Result(error=RpcError(Status.UNAVAILABLE, "full"))


async def test_a_refused_call_is_answered_as_a_full_provider_that_callers_retry(
    protocol: DubboProtocol, impl, refer, user_service
) -> None:
    url = URL.parse("dubbo://127.0.0.1:0/com.example.UserService")
    exporter = await protocol.export(url, dubbo.get_definition(user_service), _Refusing.from_implementation(impl, url))
    users = await refer(protocol, exporter)

    with pytest.raises(RpcError) as caught:
        await users.find("alice", hessian2.Long(1))

    assert not isinstance(caught.value, RemoteError)
    assert caught.value.status is Status.UNAVAILABLE
    assert caught.value.message == "SERVER_THREADPOOL_EXHAUSTED_ERROR: full"


# Keeps the frames given on stdin in flight over CONNECTIONS connections to PORT for SECONDS, each sent again once
# answered, and prints the statuses of the answers as JSON. It runs in a process of its own, as a load does: one sharing
# the event loop or the GIL of the server reads answers too late to catch it counting calls already answered.
_LOAD = """
import json, selectors, socket, struct, sys, time

port, connections, seconds = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
frames = json.load(sys.stdin)
frames = [bytes.fromhex(frame) for frame in frames]
socks = [socket.create_connection(("127.0.0.1", port)) for _ in range(connections)]
statuses = []
with selectors.DefaultSelector() as selector:
    for index, sock in enumerate(socks):
        sock.sendall(b"".join(frames[index::connections]))
        selector.register(sock, selectors.EVENT_READ, bytearray())
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for key, _ in selector.select(timeout=1):
            received = key.data
            received += key.fileobj.recv(65536)
            while len(received) >= 16 and len(received) >= 16 + int.from_bytes(received[12:16], "big"):
                _, flags, status, request_id, length = struct.unpack(">HBBqI", received[:16])
                del received[: 16 + length]
                if not flags & 0x80:
                    statuses.append(status)
                    key.fileobj.sendall(frames[request_id])
print(json.dumps(statuses))
"""


@pytest.mark.skipif(importlib.util.find_spec("uvloop") is None, reason="needs uvloop")
@pytest.mark.parametrize("anyio_backend", [pytest.param(("asyncio", {"use_uvloop": True}), id="uvloop")])
async def test_calls_answered_leave_room_at_once_for_as_many_more(protocol: DubboProtocol, impl, export, frame) -> None:
    # On uvloop, the next requests may be read before the callbacks of the calls just answered run.
    limit = 32
    exporter = await export(protocol, impl, f"?max-concurrent-calls={limit}")
    frames = [frame(0xC2, i, _request_body("find", "Ljava/lang/String;J", "alice", 1)).hex() for i in range(limit)]

    load = await anyio.run_process(
        [sys.executable, "-c", _LOAD, str(exporter.url.port), "8", "0.3"], input=json.dumps(frames).encode()
    )

    statuses = json.loads(load.stdout)
    assert len(statuses) > 1000
    assert set(statuses) == {20}


async def test_a_handler_ends_at_the_timeout_of_its_caller(protocol: DubboProtocol, impl, export, frame) -> None:
    exporter = await export(protocol, impl)
    body = hessian2.dumps_many(("2.0.2", "com.example.UserService", "0.0.0", "sleep", "", {"timeout": "50"}))

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 5, body))
        sock.setblocking(False)
        _, status, request_id, _ = await _response(sock)

    assert (status, request_id) == (31, 5)
    assert impl.started.is_set()
    assert not impl.released.is_set()


def _committing(implementation_type: type) -> Any:
    class Committing(implementation_type):
        def __init__(self) -> None:
            super().__init__()
            self.committing, self.committed = anyio.Event(), anyio.Event()

        async def sleep(self) -> str:
            with anyio.CancelScope(shield=True):
                self.committing.set()
                await anyio.sleep(0.2)
                self.committed.set()
            await anyio.sleep_forever()
            return "never"

    return Committing()


async def test_a_handler_past_the_timeout_of_its_caller_finishes_its_shielded_work_first(
    protocol: DubboProtocol, implementation_type, export, frame
) -> None:
    impl = _committing(implementation_type)
    exporter = await export(protocol, impl)
    body = hessian2.dumps_many(("2.0.2", "com.example.UserService", "0.0.0", "sleep", "", {"timeout": "50"}))

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 5, body))
        sock.setblocking(False)
        _, status, request_id, _ = await _response(sock)

    assert (status, request_id, impl.committed.is_set()) == (31, 5, True)


async def test_a_handler_whose_caller_leaves_finishes_its_shielded_work_first(
    protocol: DubboProtocol, implementation_type, export, frame
) -> None:
    impl = _committing(implementation_type)
    exporter = await export(protocol, impl)
    body = hessian2.dumps_many(("2.0.2", "com.example.UserService", "0.0.0", "sleep", "", {}))

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 5, body))
        with anyio.fail_after(2):
            await impl.committing.wait()

    with anyio.fail_after(2):
        await impl.committed.wait()


async def test_a_timeout_too_large_for_seconds_leaves_the_call_unbounded(
    protocol: DubboProtocol, impl, export, frame
) -> None:
    exporter = await export(protocol, impl)
    body = hessian2.dumps_many(
        ("2.0.2", "com.example.UserService", "0.0.0", "forget", "Ljava/lang/String;", "bob", {"timeout": "9" * 400})
    )

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 5, body))
        sock.setblocking(False)
        _, status, request_id, _ = await _response(sock)

    assert (status, request_id, impl.forgotten) == (20, 5, ["bob"])


async def test_closing_aborts_a_connection_whose_peer_stops_reading(
    protocol: DubboProtocol, export, implementation_type, user_type, address_type, frame
) -> None:
    answered, closed = anyio.Event(), anyio.Event()

    class Answering(implementation_type):
        async def find(self, name: str, user_id: int) -> Any:
            answered.set()
            return user_type(name=name, user_id=user_id, address=address_type(city="Hangzhou"))

    async def close() -> None:
        await protocol.aclose()
        closed.set()

    exporter = await export(protocol, Answering(), "?shutwait=0")
    request = frame(0xC2, 1, _request_body("find", "Ljava/lang/String;J", "x" * (4 * 1024 * 1024), 1))
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.connect(("127.0.0.1", exporter.url.port))
        sock.setblocking(False)
        await asyncio.get_running_loop().sock_sendall(sock, request)
        await answered.wait()
        await anyio.wait_all_tasks_blocked()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(close)
            with anyio.move_on_after(3):
                await closed.wait()
            closed_in_time = closed.is_set()
            sock.close()

    assert closed_in_time


async def test_a_cancelled_close_aborts_a_connection_whose_peer_stops_reading_at_once(
    protocol: DubboProtocol, export, implementation_type, user_type, address_type, frame
) -> None:
    answered = anyio.Event()

    class Answering(implementation_type):
        async def find(self, name: str, user_id: int) -> Any:
            answered.set()
            return user_type(name=name, user_id=user_id, address=address_type(city="Hangzhou"))

    exporter = await export(protocol, Answering(), "?shutwait=0")
    request = frame(0xC2, 1, _request_body("find", "Ljava/lang/String;J", "x" * (4 * 1024 * 1024), 1))
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.connect(("127.0.0.1", exporter.url.port))
        sock.setblocking(False)
        await asyncio.get_running_loop().sock_sendall(sock, request)
        await answered.wait()
        await anyio.wait_all_tasks_blocked()

        started = anyio.current_time()
        with anyio.CancelScope() as scope:
            scope.cancel()
            await protocol.aclose()

    # A graceful close would wait a second for the peer to read the response.
    assert anyio.current_time() == started


async def test_a_oneway_request_runs_without_sending_a_response(protocol, impl, export, frame):
    exporter = await export(protocol, impl)
    oneway = frame(0x82, 1, _request_body("forget", "Ljava/lang/String;", "bob"))
    twoway = frame(0xC2, 2, _request_body("forget", "Ljava/lang/String;", "alice"))

    async with await anyio.connect_tcp("127.0.0.1", exporter.url.port) as stream:
        await stream.send(oneway)
        await anyio.wait_all_tasks_blocked()
        await stream.send(twoway)
        reader = BufferedByteReceiveStream(stream)
        header = await reader.receive_exactly(16)
        _, flags, status, request_id, length = struct.unpack(">HBBqI", header)
        await reader.receive_exactly(length)

    assert (flags, status, request_id) == (2, 20, 2)
    assert impl.forgotten == ["bob", "alice"]


async def test_a_request_that_cannot_be_read_is_answered_bad_request(
    protocol: DubboProtocol, impl, export, frame
) -> None:
    exporter = await export(protocol, impl)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 9, hessian2.dumps_many(["not", "a", "request"])))
        sock.setblocking(False)
        header = await _receive(sock, 16)

    magic, flags, status, request_id, _ = struct.unpack(">HBBqI", header)
    assert (magic, flags & 0x80, status, request_id) == (0xDABB, 0, 40, 9)


@pytest.mark.parametrize(
    ("method", "descriptor"), [("find", "Ljava/lang/String;I"), ("find", ""), ("missing", "")], ids=repr
)
async def test_a_request_whose_descriptor_matches_no_method_is_not_found(
    protocol: DubboProtocol, impl, method: str, descriptor: str, export, frame
) -> None:
    exporter = await export(protocol, impl)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 3, _request_body(method, descriptor, "bob", 1)))
        sock.setblocking(False)
        _, status, request_id, body = await _response(sock)

    assert (status, request_id) == (60, 3)
    assert f"{method}({descriptor})" in hessian2.loads(body)


@pytest.mark.parametrize("arguments", [(1, 7), ("bob", "seven")], ids=repr)
async def test_arguments_of_other_types_are_answered_bad_request(
    protocol: DubboProtocol, impl, arguments: tuple[Any, ...], export, frame
) -> None:
    exporter = await export(protocol, impl)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 4, _request_body("find", "Ljava/lang/String;J", *arguments)))
        sock.setblocking(False)
        _, status, _, body = await _response(sock)

    assert status == 40
    assert "cannot read the request" in hessian2.loads(body)


async def test_a_group_that_is_no_text_is_answered_bad_request(protocol: DubboProtocol, impl, export, frame) -> None:
    exporter = await export(protocol, impl)
    values = ("2.0.2", "com.example.UserService", "0.0.0", "find", "Ljava/lang/String;J", "bob", 1, {"group": ["a"]})

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 6, hessian2.dumps_many(values)))
        sock.setblocking(False)
        _, status, _, _ = await _response(sock)

    assert status == 40


@pytest.mark.parametrize(
    ("path", "attachments"), [("com.example.Other", {}), ("com.example.UserService", {"group": "missing"})], ids=repr
)
async def test_echo_answers_only_for_exported_services(
    protocol: DubboProtocol, impl, path: str, attachments: dict[str, str], export, frame
) -> None:
    exporter = await export(protocol, impl)
    values = ("2.0.2", path, "0.0.0", "$echo", "Ljava/lang/Object;", "ping", attachments)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 7, hessian2.dumps_many(values)))
        sock.setblocking(False)
        _, status, _, _ = await _response(sock)

    assert status == 60


@pytest.mark.parametrize(("serialization_id", "name"), [(23, "fastjson2 (23)"), (30, "serialization 30")])
async def test_a_request_in_another_serialization_is_answered_with_a_serialization_error(
    protocol: DubboProtocol, impl, serialization_id: int, name: str, export, frame
) -> None:
    exporter = await export(protocol, impl)

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC0 | serialization_id, 5, b"{}"))
        sock.setblocking(False)
        header = await _receive(sock, 16)
        _, flags, status, request_id, length = struct.unpack(">HBBqI", header)
        body = await _receive(sock, length)

    assert (flags & 0x1F, status, request_id) == (2, 25, 5)
    assert hessian2.loads(body) == f"the request is in {name}, but this server reads hessian2 (2)"


async def test_a_handler_sees_an_ipv6_caller_with_its_host_in_brackets(
    protocol: DubboProtocol, implementation_type, user_service
) -> None:
    peers: list[str | None] = []

    class Recording(implementation_type):
        async def find(self, name: str, user_id: int) -> Any:
            peers.append(dubbo.incoming().peer)
            return None

    url = URL.parse("dubbo://[::1]:0/com.example.UserService")
    definition = dubbo.get_definition(user_service)
    exporter = await protocol.export(url, definition, ServiceInvoker.from_implementation(Recording(), url))
    caller = URL.parse(f"dubbo://[::1]:{exporter.url.port}/com.example.UserService")
    users = proxy(user_service, (await protocol.refer(caller, definition)).invoke)

    await users.find("bob", hessian2.Long(1))

    assert (peers[0] or "").startswith("[::1]:")


async def test_a_tls_handshake_takes_at_most_the_ssl_handshake_timeout(protocol: DubboProtocol, impl, export) -> None:
    certificates = Path(__file__).resolve().parents[3] / "certificates"
    query = (
        f"?ssl-enabled=true&tls-cert-file={certificates / 'localhost-cert.pem'}"
        f"&tls-key-file={certificates / 'localhost-key.pem'}&ssl-handshake-timeout=100"
    )
    exporter = await export(protocol, impl, query)

    # A client that never starts its handshake.
    async with await anyio.connect_tcp("127.0.0.1", exporter.url.port) as stream:
        with anyio.fail_after(5), pytest.raises((anyio.EndOfStream, anyio.BrokenResourceError)):
            await stream.receive()


@pytest.mark.parametrize("types", [None, []], ids=["null-types", "no-types"])
async def test_a_generic_call_without_arguments_may_send_null_for_them(
    protocol: DubboProtocol, impl, export, frame, types
) -> None:
    exporter = await export(protocol, impl)
    impl.released.set()
    descriptor = "Ljava/lang/String;[Ljava/lang/String;[Ljava/lang/Object;"

    with socket.create_connection(("127.0.0.1", exporter.url.port)) as sock:
        sock.sendall(frame(0xC2, 5, _request_body("$invoke", descriptor, "sleep", types, None)))
        sock.setblocking(False)
        _, status, request_id, _ = await _response(sock)

    assert (status, request_id) == (20, 5)
    assert impl.started.is_set()
