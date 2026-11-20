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

import os
import signal
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import pytest

from dubbo import Dubbo

pytestmark = pytest.mark.anyio
APP = {"application": {"name": "orders"}}


@pytest.mark.skipif(sys.platform == "win32", reason="signals are not received on Windows")
async def test_serve_forever_returns_on_sigterm():
    async def terminate() -> None:
        await anyio.wait_all_tasks_blocked()
        os.kill(os.getpid(), signal.SIGTERM)

    async with Dubbo(APP, env_prefix=None) as app:
        with anyio.fail_after(5):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(terminate)
                await app.serve_forever()


@pytest.mark.skipif(sys.platform == "win32", reason="signals are not received on Windows")
async def test_a_second_signal_while_stopping_stops_at_once():
    async def terminate() -> None:
        await anyio.wait_all_tasks_blocked()
        os.kill(os.getpid(), signal.SIGTERM)

    @asynccontextmanager
    async def stalls(app: Dubbo) -> AsyncIterator[None]:
        yield
        os.kill(os.getpid(), signal.SIGINT)
        await anyio.sleep_forever()

    with anyio.fail_after(5):
        async with (
            Dubbo({**APP, "shutdown": {"grace": 60}}, lifespan=stalls, env_prefix=None) as app,
            anyio.create_task_group() as task_group,
        ):
            task_group.start_soon(terminate)
            await app.serve_forever()

    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@pytest.mark.parametrize("loop", ["asyncio", "uvloop"])
def test_serve_forever_outside_the_main_thread_serves_until_cancelled(loop):
    if loop == "uvloop":
        pytest.importorskip("uvloop")
    outcome = []

    async def serve() -> None:
        async with Dubbo(APP, env_prefix=None) as app:
            with anyio.move_on_after(0.1) as scope:
                await app.serve_forever()
        outcome.append(scope.cancelled_caught)

    def run() -> None:
        try:
            anyio.run(serve, backend_options={"use_uvloop": loop == "uvloop"})
        except BaseException as error:
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(5)

    assert outcome == [True]
