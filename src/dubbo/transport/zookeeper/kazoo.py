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

import contextlib
import functools
import logging
import posixpath
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from typing import Any, Self, TypeVar

import anyio
import attrs
from anyio import from_thread, to_thread
from anyio.lowlevel import EventLoopToken, current_token

from dubbo.constants import BACKUP_KEY, SESSION_KEY, TIMEOUT_KEY
from dubbo.url import URL
from dubbo.utils import Latest, backoff, release_scope, require_optional_dependency
from dubbo.utils.converters import milliseconds

from .base import ZookeeperClient
from .exceptions import ZookeeperError

with require_optional_dependency("kazoo", extra="zookeeper"):
    from kazoo.client import KazooClient
    from kazoo.exceptions import BadVersionError, KazooException, NodeExistsError, NoNodeError, SessionExpiredError
    from kazoo.handlers.threading import KazooTimeoutError
    from kazoo.interfaces import IAsyncResult
    from kazoo.protocol.states import KazooState, ZnodeStat
    from kazoo.security import CREATOR_ALL_ACL

__all__ = ["KazooZookeeperClient"]

T = TypeVar("T")

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0  # Seconds.
_DEFAULT_SESSION = 60.0  # Seconds.
# Reconnects without end, waiting at most a second between rounds of the hosts, so that a client connects again soon
# after ZooKeeper recovers from an outage of any length.
_CONNECTION_RETRY = {"max_tries": -1, "delay": 0.1, "backoff": 2, "max_delay": 1.0}


class KazooZookeeperClient(ZookeeperClient):
    """A ``ZookeeperClient`` backed by kazoo.

    kazoo blocks and calls back from threads of its own. Its calls run in
    worker threads, waiting at most the URL's ``timeout``, and its
    callbacks hand their values to the event loop that connected. kazoo
    parses the hosts, with port 2181 by default. With a user, the nodes it
    creates are open only to that user.
    """

    def __init__(self, url: URL) -> None:
        super().__init__(url)

        backups = url.parameters.get(BACKUP_KEY)
        auth = None if url.userinfo is None else [("digest", url.userinfo)]

        self._hosts = url.address + (f",{backups}" if backups else "")
        self._timeout = _positive_seconds(url, TIMEOUT_KEY, _DEFAULT_TIMEOUT)
        session = _positive_seconds(url, SESSION_KEY, _DEFAULT_SESSION)
        acl = None if auth is None else CREATOR_ALL_ACL
        self._kazoo = KazooClient(
            hosts=self._hosts, timeout=session, auth_data=auth, default_acl=acl, connection_retry=_CONNECTION_RETRY
        )
        self._token: EventLoopToken | None = None

        # The ephemeral nodes to create again in each new session, by path. Only kazoo and worker threads take the
        # lock, which they hold across network calls.
        self._ephemeral: dict[str, _Ephemeral] = {}
        # One lock per kept path, so that the nodes of other paths do not wait for one; the lock of the map is never
        # held across a call to the server.
        self._path_locks: dict[str, tuple[threading.Lock, list[int]]] = {}
        self._path_locks_lock = threading.Lock()
        self._lost = False
        # Counts the new sessions, so that the recovery of an earlier one stops.
        self._session = 0
        self._closed = threading.Event()

    async def get(self, path: str) -> bytes | None:
        def get() -> bytes | None:
            try:
                data, _stat = self._wait(self._kazoo.get_async(path))
            except NoNodeError:
                return None
            return data

        return await self._run(get, f"get {path}")

    @asynccontextmanager
    async def keep_ephemeral(self, path: str, data: bytes = b"") -> AsyncGenerator[None]:
        node = _Ephemeral(data=data)
        # The name of a node may hold a URL with a token, so errors name its parent.
        parent = posixpath.dirname(path)

        def create() -> None:
            with self._path_locked(path):
                # The keeper was cancelled before the call began.
                if node.released:
                    return
                replaced = self._ephemeral.get(path)
                self._ephemeral[path] = node
                try:
                    self._create_ephemeral(path, data)
                except BaseException:
                    # The node may have been created, or the one replaced deleted, before the failure.
                    with contextlib.suppress(KazooException, KazooTimeoutError):
                        if replaced is None or replaced.released:
                            del self._ephemeral[path]
                            self._wait(self._kazoo.delete_async(path))
                        else:
                            self._ephemeral[path] = replaced
                            self._create_ephemeral(path, replaced.data)
                    raise

        def delete() -> None:
            with self._path_locked(path):
                # A later keeper of the path has replaced the node.
                if self._ephemeral.get(path) is not node:
                    return
                del self._ephemeral[path]
                # The session of a closed client, or an expired one, has deleted the node.
                if not self._closed.is_set():
                    with contextlib.suppress(NoNodeError, SessionExpiredError):
                        self._wait(self._kazoo.delete_async(path))

        try:
            await self._run(create, f"create a node in {parent}")
            yield
        finally:
            # Released at once, so that a new session no longer creates the node; a cancelled exit leaves deleting
            # it to the worker thread, or to the session.
            node.released = True
            await self._run(delete, f"delete a node in {parent}")

    async def update(self, path: str, change: Callable[[bytes | None], bytes]) -> None:
        def update() -> None:
            while True:
                try:
                    data, stat = self._wait(self._kazoo.get_async(path))
                except NoNodeError:
                    try:
                        self._wait(self._kazoo.create_async(path, change(None), makepath=True))
                    except NodeExistsError:
                        continue
                    return

                changed = change(data)
                if changed == data:
                    return
                try:
                    self._wait(self._kazoo.set_async(path, changed, version=stat.version))
                except (BadVersionError, NoNodeError):
                    continue
                return

        await self._run(update, f"update {path}")

    @asynccontextmanager
    async def watch(self, path: str) -> AsyncGenerator[AsyncIterator[bytes | None]]:
        latest: Latest[bytes | None] = Latest()

        recipes: list[Any] = []

        def changed(data: bytes | None, _stat: object) -> bool:
            return self._publish(latest, data)

        def register() -> None:
            recipes.append(self._kazoo.DataWatch(path, changed))

        async with self._watching(latest, register, recipes, f"watch {path}"):
            yield aiter(latest)

    @asynccontextmanager
    async def watch_children(self, path: str) -> AsyncGenerator[AsyncIterator[list[str]]]:
        latest: Latest[list[str]] = Latest()
        # kazoo's ChildrenWatch stops for good once its node is deleted, so a
        # DataWatch follows the node and starts one for each node created at
        # path, told apart by its creation zxid. A watch left from an earlier
        # node stops when it next calls back.
        following: int | None = None
        recipes: list[Any] = []

        def node_changed(_data: bytes | None, stat: ZnodeStat | None) -> bool:
            nonlocal following

            if stat is None:
                following = None
                return self._publish(latest, [])
            if latest.closed or stat.czxid == following:
                return not latest.closed

            following = stat.czxid
            try:
                recipes.append(self._kazoo.ChildrenWatch(path, functools.partial(children_changed, stat.czxid)))
            except Exception:
                # The next change of the node tries again.
                following = None
                raise
            return True

        def children_changed(node: int, children: list[str]) -> bool:
            return node == following and self._publish(latest, children)

        def register() -> None:
            recipes.append(self._kazoo.DataWatch(path, node_changed))

        async with self._watching(latest, register, recipes, f"watch the children of {path}"):
            yield aiter(latest)

    async def aclose(self) -> None:
        self._closed.set()

        def close() -> None:
            self._kazoo.stop()
            self._kazoo.close()

        # Whatever the wait ends with, the thread finishes disconnecting alone.
        with release_scope(self._timeout):
            await to_thread.run_sync(close, abandon_on_cancel=True)

    async def __aenter__(self) -> Self:
        self._token = current_token()
        self._kazoo.add_listener(self._state_changed)
        # start stops and closes the client itself when it times out.
        await self._run(lambda: self._kazoo.start(self._timeout), "connect")
        return self

    def _create_ephemeral(self, path: str, data: bytes) -> None:
        try:
            self._wait(self._kazoo.create_async(path, data, ephemeral=True, makepath=True))
        except NodeExistsError:
            stat = self._wait(self._kazoo.exists_async(path))
            session = self._kazoo.client_id
            if stat is not None and session is not None and stat.ephemeralOwner == session[0]:
                # The node of this session changes in place, so that watchers never see it missing.
                self._wait(self._kazoo.set_async(path, data))
                return
            # A node left by an expired session must belong to this one.
            self._wait(self._kazoo.delete_async(path))
            self._wait(self._kazoo.create_async(path, data, ephemeral=True, makepath=True))

    def _state_changed(self, state: str) -> None:
        # kazoo calls listeners from its connection thread, which must not block.
        if state == KazooState.LOST:
            self._lost = True
        elif state == KazooState.CONNECTED and self._lost:
            self._lost = False
            self._session += 1
            self._kazoo.handler.spawn(self._create_ephemeral_again, self._session)

    @contextlib.contextmanager
    def _path_locked(self, path: str) -> Generator[None]:
        """Hold the lock of ``path``, which orders the creating and deleting of its node, in a thread."""
        with self._path_locks_lock:
            lock, users = self._path_locks.setdefault(path, (threading.Lock(), [0]))
            users[0] += 1
        try:
            with lock:
                yield
        finally:
            with self._path_locks_lock:
                users[0] -= 1
                if not users[0]:
                    del self._path_locks[path]

    def _create_ephemeral_again(self, session: int) -> None:
        """Create the ephemeral nodes again in a new session, in a thread of kazoo.

        A node that cannot be created does not hold up the others; those
        that failed are tried again after a delay until they are created,
        the session is replaced or the client closes.
        """
        delays = backoff()
        # Keepers of other paths change the map meanwhile; copying it is atomic.
        pending = list(self._ephemeral.copy())
        while True:
            pending = [path for path in pending if not self._try_create(path)]
            if not pending:
                return
            parents = ", ".join(sorted({posixpath.dirname(path) for path in pending}))
            _logger.warning("Cannot create the nodes in %s again on ZooKeeper %s; retrying", parents, self._hosts)
            if self._closed.wait(next(delays)) or session != self._session:
                return

    def _try_create(self, path: str) -> bool:
        """Create the node kept at ``path`` again, unless its keeper has exited; return whether nothing is left to do."""
        # Only the keeper of this path waits for it.
        with self._path_locked(path):
            node = self._ephemeral.get(path)
            if node is None or node.released:
                return True
            try:
                self._create_ephemeral(path, node.data)
            except (KazooException, KazooTimeoutError):
                _logger.debug("Cannot create a node in %s again", posixpath.dirname(path), exc_info=True)
                return False
        return True

    @asynccontextmanager
    async def _watching(
        self, latest: Latest[T], register: Callable[[], None], recipes: list[Any], action: str
    ) -> AsyncGenerator[None]:
        """Register kazoo watches, which ``register`` adds to ``recipes`` and which publish to ``latest``, and stop them on exit.

        kazoo calls the watch function once while registering, then after
        each change; it drops the watch when the function returns false.
        """
        try:
            try:
                # kazoo retries the first read of a watch without limit while
                # disconnected; an abandoned registration ends when it publishes.
                with anyio.fail_after(self._timeout):
                    await self._run(register, action)
            except TimeoutError as error:
                raise ZookeeperError(f"cannot {action}: timed out") from error

            yield
        finally:
            latest.close()
            for recipe in recipes:
                self._stop(recipe)

    def _stop(self, recipe: Any) -> None:
        """Stop a kazoo ``DataWatch`` or ``ChildrenWatch`` now, which kazoo does only when its function next returns false.

        kazoo has no call for it, so this sets what its recipes set to stop themselves, and drops their callbacks.
        """
        # shortcut: uses kazoo private attributes; switch to a public stop once kazoo has one.
        # Not under the recipe's lock, which kazoo holds across its reads: a read in progress calls back once more,
        # and the function of the closed watch returns false.
        recipe._stopped = True
        self._kazoo.remove_listener(recipe._session_watcher)
        for watchers in (self._kazoo._data_watchers, self._kazoo._child_watchers):
            if recipe._path in watchers:
                watchers[recipe._path].discard(recipe._watcher)

    def _publish(self, latest: Latest[T], value: T) -> bool:
        """Hand a value from a kazoo thread to the event loop; return False once the watch has ended."""
        if latest.closed:
            return False
        try:
            from_thread.run_sync(latest.publish, value, token=self._token)
        except RuntimeError:
            return False  # The event loop has ended.
        return True

    def _wait(self, result: IAsyncResult) -> T:
        return result.get(timeout=self._timeout)

    async def _run(self, call: Callable[[], T], action: str) -> T:
        """Run a blocking kazoo call in a worker thread, raising ZookeeperError for kazoo errors.

        A cancelled call returns at once and leaves the thread to finish.
        """
        try:
            return await to_thread.run_sync(call, abandon_on_cancel=True)
        except (KazooException, KazooTimeoutError) as error:
            raise ZookeeperError(f"cannot {action} on ZooKeeper {self._hosts}") from error


@attrs.define(kw_only=True, eq=False)
class _Ephemeral:
    """An ephemeral node a keeper keeps: its data, and whether the keeper has exited."""

    data: bytes
    released: bool = False


def _positive_seconds(url: URL, key: str, default: float) -> float:
    seconds = url.get_parameter(key, milliseconds, default)
    if seconds <= 0:
        raise ValueError(f"URL parameter {key!r} must be positive")
    return seconds
