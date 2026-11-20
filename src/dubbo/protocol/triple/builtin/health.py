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

"""The gRPC health service, grpc.health.v1.Health."""

from collections.abc import Collection

import anyio

from dubbo._proto.grpc.health.v1.health_dubbo import Health, HealthServicer
from dubbo._proto.grpc.health.v1.health_pb2 import (
    HealthCheckRequest,
    HealthCheckResponse,
    HealthListRequest,
    HealthListResponse,
)
from dubbo.exceptions import RpcError, Status
from dubbo.rpc.stream import SendStream

__all__ = ["Health", "HealthService"]

_SERVING = HealthCheckResponse.SERVING
_NOT_SERVING = HealthCheckResponse.NOT_SERVING
_SERVICE_UNKNOWN = HealthCheckResponse.SERVICE_UNKNOWN


class HealthService(HealthServicer):
    """Reports the health of a server: SERVING for the server as a whole, named ``""``, and for each service it serves.

    A service is known by its interface and by its service key. One that
    stops being served stays known as NOT_SERVING. Once the application
    announces its shutdown, everything is NOT_SERVING; once the server
    closes, watches end too.
    """

    def __init__(self) -> None:
        self._statuses: dict[str, HealthCheckResponse.ServingStatus] = {"": _SERVING}
        self._stopping = False
        self._closed = False
        # Replaced after every change, so a watch never misses one.
        self._changed = anyio.Event()

    def update(self, services: Collection[str]) -> None:
        """Report ``services`` as serving, and the other services known before as not serving."""
        if self._stopping:
            return

        statuses = dict.fromkeys(self._statuses, _NOT_SERVING) | dict.fromkeys(services, _SERVING)
        statuses[""] = _SERVING
        self._change(statuses)

    def announce_shutdown(self) -> None:
        """Report everything as not serving from now on, while the watches go on."""
        self._stopping = True
        self._change(dict.fromkeys(self._statuses, _NOT_SERVING))

    def close(self) -> None:
        """Report everything as not serving, ending the watches."""
        if self._closed:
            return

        self._stopping = self._closed = True
        self._statuses = dict.fromkeys(self._statuses, _NOT_SERVING)
        self._wake()

    async def check(self, request: HealthCheckRequest) -> HealthCheckResponse:
        status = self._statuses.get(request.service)
        if status is None:
            raise RpcError(Status.NOT_FOUND, f"unknown service {request.service!r}")
        return HealthCheckResponse(status=status)

    async def list(self, request: HealthListRequest) -> HealthListResponse:
        return HealthListResponse(
            statuses={name: HealthCheckResponse(status=status) for name, status in self._statuses.items()}
        )

    async def watch(self, request: HealthCheckRequest, stream: SendStream[HealthCheckResponse]) -> None:
        sent = None
        while True:
            changed = self._changed
            status = self._statuses.get(request.service, _SERVICE_UNKNOWN)
            if status != sent:
                await stream.send(HealthCheckResponse(status=status))
                sent = status

            if self._closed:
                return
            await changed.wait()

    def _change(self, statuses: dict[str, HealthCheckResponse.ServingStatus]) -> None:
        if statuses == self._statuses:
            return

        self._statuses = statuses
        self._wake()

    def _wake(self) -> None:
        self._changed.set()
        self._changed = anyio.Event()
