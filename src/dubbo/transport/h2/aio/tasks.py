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

__all__ = ["join_shielded"]


async def join_shielded(task: asyncio.Task[None]) -> None:
    """Wait until ``task`` finishes even when the caller is cancelled, then raise that cancellation or its error.

    AnyIO cancellation stays out while waiting, and `asyncio.Task.cancel` on the
    caller is held until ``task`` is done; ``task`` itself is never cancelled.
    """
    cancelled = False
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.wait((task,))
            except asyncio.CancelledError:
                cancelled = True

    if cancelled:
        raise asyncio.CancelledError
    task.result()
