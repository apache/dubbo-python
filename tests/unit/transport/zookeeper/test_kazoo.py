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

import itertools
import logging
import threading
from types import SimpleNamespace

import anyio
import pytest
from kazoo.exceptions import KazooException, NoNodeError, SessionExpiredError
from kazoo.protocol.states import KazooState
from kazoo.security import CREATOR_ALL_ACL

from dubbo.transport.zookeeper import ZookeeperError, kazoo
from dubbo.transport.zookeeper.kazoo import KazooZookeeperClient
from dubbo.url import URL

# The client calls kazoo in threads, which these tests drive and wait for.
pytestmark = pytest.mark.real_clock


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("zookeeper://zk?timeout=1.5", "'timeout': must be whole milliseconds"),
        ("zookeeper://zk?session=0", "'session' must be positive"),
    ],
)
def test_kazoo_rejects_times_that_are_not_positive_milliseconds(text, message):
    with pytest.raises(ValueError, match=message):
        KazooZookeeperClient(URL.parse(text))


class _Result:
    def __init__(self, value=None, gate=None):
        self.value = value
        self.gate = gate

    def get(self, timeout):
        # A gated result waits as a network call does, until its test opens the gate.
        if self.gate is not None:
            self.gate.waiting.set()
            assert self.gate.wait(5)
        return self.value


class _Gate(threading.Event):
    def __init__(self):
        super().__init__()
        self.waiting = threading.Event()

    def open_later(self, seconds=1.0):
        threading.Timer(seconds, self.set).start()


class _Kazoo:
    def __init__(self, **settings):
        self.settings = settings
        self.listeners = []
        self.nodes = {}
        self.created = []
        self.deleted = []
        self.failures = {}
        self.gates = {}
        self.jobs = []
        self.handler = SimpleNamespace(spawn=lambda function, *args: self.jobs.append((function, args)))
        self.replaced = False
        self.expired = False
        self._data_watchers = {}
        self._child_watchers = {}

    def start(self, timeout):
        pass

    def stop(self):
        pass

    def close(self):
        pass

    def add_listener(self, listener):
        self.listeners.append(listener)

    def remove_listener(self, listener):
        pass

    def get_async(self, path):
        return _Result((self.nodes.get(path), None), self.gates.get(path))

    def create_async(self, path, data, **options):
        if self.failures.get(path, 0):
            self.failures[path] -= 1
            if self.replaced:
                self.new_session()
            raise KazooException("unreachable")
        self.nodes[path] = data
        self.created.append(path)
        return _Result(path, self.gates.get(path))

    def delete_async(self, path):
        if self.expired:
            raise SessionExpiredError()
        if self.nodes.pop(path, None) is None:
            raise NoNodeError(path)
        self.deleted.append(path)
        return _Result()

    def new_session(self):
        self.nodes.clear()
        for state in (KazooState.LOST, KazooState.CONNECTED):
            for listener in self.listeners:
                listener(state)

    def recover(self):
        function, args = self.jobs.pop(0)
        function(*args)


@pytest.fixture
def backend(monkeypatch):
    backend = _Kazoo()
    monkeypatch.setattr(kazoo, "KazooClient", lambda **settings: backend.settings.update(settings) or backend)
    monkeypatch.setattr(kazoo, "backoff", lambda: itertools.repeat(0))
    return backend


@pytest.mark.parametrize(
    ("text", "acl"),
    [("zookeeper://alice:secret@zk", CREATOR_ALL_ACL), ("zookeeper://zk", None)],
    ids=["with-user", "anonymous"],
)
def test_kazoo_creates_nodes_open_only_to_its_user(text, acl, backend):
    KazooZookeeperClient(URL.parse(text))

    assert backend.settings["default_acl"] == acl


def test_kazoo_waits_at_most_a_second_between_rounds_of_reconnecting():
    retry = KazooZookeeperClient(URL.parse("zookeeper://zk"))._kazoo._conn_retry

    assert (retry.max_tries, retry.max_delay) == (-1, 1.0)


@pytest.mark.anyio
async def test_ephemeral_recovery_retries_failed_nodes_without_delaying_the_others(backend):
    async with (
        KazooZookeeperClient(URL.parse("zookeeper://zk")) as client,
        client.keep_ephemeral("/a", b"a"),
        client.keep_ephemeral("/b", b"b"),
    ):
        backend.created.clear()
        backend.failures["/a"] = 2

        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

        assert backend.created == ["/b", "/a"]
        assert backend.nodes == {"/a": b"a", "/b": b"b"}


@pytest.mark.anyio
async def test_ephemeral_recovery_stops_when_another_session_replaces_it(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client, client.keep_ephemeral("/a"):
        backend.failures["/a"] = 2
        backend.replaced = True

        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

        assert backend.failures["/a"] == 1
        assert backend.nodes == {}


@pytest.mark.anyio
async def test_a_node_kept_is_deleted_on_exit_and_no_longer_created_again(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        async with client.keep_ephemeral("/a", b"a"):
            kept = dict(backend.nodes)
        backend.created.clear()

        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

    assert (kept, backend.deleted, backend.created) == ({"/a": b"a"}, ["/a"], [])


@pytest.mark.anyio
async def test_a_node_kept_exits_quietly_once_its_session_has_expired(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        async with client.keep_ephemeral("/a"):
            backend.expired = True

        backend.expired = False
        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

    assert backend.nodes == {}


@pytest.mark.anyio
async def test_a_later_keeper_replaces_the_node_and_the_earlier_one_leaves_it_on_exit(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        earlier = client.keep_ephemeral("/a", b"old")
        await earlier.__aenter__()
        async with client.keep_ephemeral("/a", b"new"):
            await earlier.__aexit__(None, None, None)
            left = dict(backend.nodes)

    assert (left, backend.nodes, backend.deleted) == ({"/a": b"new"}, {}, ["/a"])


@pytest.mark.anyio
async def test_a_keeper_that_fails_to_replace_a_node_restores_the_one_kept_before(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client, client.keep_ephemeral("/a", b"old"):
        backend.failures["/a"] = 1
        with pytest.raises(ZookeeperError):
            async with client.keep_ephemeral("/a", b"new"):
                pytest.fail("the node was not created")
        restored = dict(backend.nodes)

        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

        assert (restored, backend.nodes) == ({"/a": b"old"}, {"/a": b"old"})


@pytest.mark.anyio
async def test_a_keeper_that_fails_is_not_created_again_in_a_new_session(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        backend.failures["/a"] = 1
        with pytest.raises(ZookeeperError):
            async with client.keep_ephemeral("/a"):
                pytest.fail("the node was not created")

        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

    assert (backend.nodes, backend.created) == ({}, [])


@pytest.mark.anyio
async def test_a_cancelled_watch_rejects_its_abandoned_registration_callback(backend):
    registering, release, finished = threading.Event(), threading.Event(), threading.Event()
    accepted = []

    def register(path, changed):
        registering.set()
        assert release.wait(2)
        accepted.append(changed(b"late", None))
        finished.set()
        return object()

    backend.DataWatch = register
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        with anyio.fail_after(2):
            async with anyio.create_task_group() as tasks:

                async def watch():
                    async with client.watch("/a"):
                        pytest.fail("registration was not cancelled")

                tasks.start_soon(watch)
                assert await anyio.to_thread.run_sync(registering.wait, 1)
                tasks.cancel_scope.cancel()

            release.set()
            assert await anyio.to_thread.run_sync(finished.wait, 1)

    assert accepted == [False]


@pytest.mark.anyio
async def test_leaving_a_kept_node_does_not_wait_while_another_is_being_created(backend):
    backend.gates["/b"] = gate = _Gate()
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        kept = client.keep_ephemeral("/a")
        await kept.__aenter__()
        async with anyio.create_task_group() as tasks:

            async def keep_another():
                async with client.keep_ephemeral("/b"):
                    pass

            tasks.start_soon(keep_another)
            assert await anyio.to_thread.run_sync(gate.waiting.wait, 5)
            # Leaving "/a" deletes it while "/b" is still being created; were it waiting for that, the bound would end
            # the test.
            try:
                with anyio.fail_after(5):
                    await kept.__aexit__(None, None, None)
                assert "/a" in backend.deleted
                assert not gate.is_set()
            finally:
                gate.set()


@pytest.mark.anyio
async def test_a_cancelled_exit_of_a_kept_node_returns_while_another_is_being_created(backend):
    backend.gates["/b"] = gate = _Gate()
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        kept = client.keep_ephemeral("/a")
        await kept.__aenter__()
        async with anyio.create_task_group() as tasks:

            async def keep_another():
                async with client.keep_ephemeral("/b"):
                    pass

            tasks.start_soon(keep_another)
            assert await anyio.to_thread.run_sync(gate.waiting.wait, 5)
            # Deleting "/a" waits for "/b" to be created; a cancelled exit leaves that to the worker thread.
            try:
                with anyio.fail_after(5):
                    async with anyio.create_task_group() as leaving:
                        leaving.start_soon(kept.__aexit__, None, None, None)
                        await anyio.wait_all_tasks_blocked()
                        leaving.cancel_scope.cancel()
                assert not gate.is_set()
            finally:
                gate.set()

        while "/a" not in backend.deleted:
            await anyio.sleep(0.01)
        backend.created.clear()
        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

    assert backend.created == []


@pytest.mark.anyio
async def test_leaving_a_watch_does_not_wait_for_a_read_in_progress(backend):
    recipe = SimpleNamespace(
        _run_lock=threading.Lock(), _stopped=False, _session_watcher=None, _path="/a", _watcher=None
    )
    backend.DataWatch = lambda path, changed: recipe
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        watch = client.watch("/a")
        await watch.__aenter__()
        # kazoo holds the lock of a recipe while it reads; it is held until the watch has been left.
        recipe._run_lock.acquire()
        try:
            with anyio.fail_after(5):
                await watch.__aexit__(None, None, None)
        finally:
            recipe._run_lock.release()

    assert recipe._stopped


@pytest.mark.anyio
async def test_a_cancelled_read_returns_without_waiting_for_the_server(backend):
    backend.gates["/a"] = gate = _Gate()
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        try:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as tasks:

                    async def read():
                        await client.get("/a")

                    tasks.start_soon(read)
                    assert await anyio.to_thread.run_sync(gate.waiting.wait, 5)
                    tasks.cancel_scope.cancel()

            # It returned while the server still had not answered.
            assert not gate.is_set()
        finally:
            gate.set()


@pytest.mark.anyio
async def test_a_cancelled_update_returns_without_waiting_for_the_server(backend):
    backend.gates["/a"] = gate = _Gate()
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        try:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as tasks:

                    async def update():
                        await client.update("/a", lambda data: b"x")

                    tasks.start_soon(update)
                    assert await anyio.to_thread.run_sync(gate.waiting.wait, 5)
                    tasks.cancel_scope.cancel()

            # It returned while the server still had not answered.
            assert not gate.is_set()
        finally:
            gate.set()


@pytest.mark.anyio
async def test_a_keeper_cancelled_while_creating_returns_at_once_and_keeps_nothing(backend):
    backend.gates["/a"] = gate = _Gate()
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        try:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as tasks:

                    async def keep():
                        async with client.keep_ephemeral("/a"):
                            pytest.fail("the node was kept")

                    tasks.start_soon(keep)
                    assert await anyio.to_thread.run_sync(gate.waiting.wait, 5)
                    tasks.cancel_scope.cancel()

            # It returned while the server still had not answered.
            assert not gate.is_set()
        finally:
            gate.set()
        backend.created.clear()
        backend.new_session()
        await anyio.to_thread.run_sync(backend.recover)

    assert backend.created == []


class _FirstHeldLock:
    """A lock that holds back the first thread to take it until ``go`` is set, then sets ``first_done`` as it leaves."""

    def __init__(self):
        self.go, self.first_done = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._first = None

    def __enter__(self):
        if self._first is None:
            self._first = threading.get_ident()
            assert self.go.wait(5)
        self._lock.acquire()

    def __exit__(self, *exc_info):
        self._lock.release()
        if threading.get_ident() == self._first:
            self.first_done.set()


@pytest.mark.anyio
async def test_a_keeper_cancelled_before_its_call_begins_never_creates_the_node(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        lock = _FirstHeldLock()
        client._path_locked = lambda path: lock
        with anyio.move_on_after(0.1):
            async with client.keep_ephemeral("/a"):
                pytest.fail("the node was kept")

        lock.go.set()
        assert await anyio.to_thread.run_sync(lock.first_done.wait, 5)

    assert backend.created == []


@pytest.mark.anyio
async def test_failures_to_keep_a_node_name_its_parent_only(backend, caplog):
    path = "/root/providers/tri%3A%2F%2Fhost%3Ftoken%3Dsecret"
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        backend.failures[path] = 1
        with pytest.raises(ZookeeperError, match="/root/providers") as caught:
            async with client.keep_ephemeral(path):
                pytest.fail("the node was not created")

        async with client.keep_ephemeral(path):
            backend.failures[path] = 1
            backend.new_session()
            with caplog.at_level(logging.DEBUG, logger=kazoo.__name__):
                await anyio.to_thread.run_sync(backend.recover)

    assert "secret" not in str(caught.value)
    assert "/root/providers" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.anyio
async def test_the_lock_of_a_path_is_dropped_once_no_keeper_uses_it(backend):
    async with KazooZookeeperClient(URL.parse("zookeeper://zk")) as client:
        for path in ("/a", "/b", "/a"):
            async with client.keep_ephemeral(path):
                pass

        assert client._path_locks == {}
