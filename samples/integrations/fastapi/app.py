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

# The gateway of the shop: a FastAPI application that answers each HTTP
# request with calls to the services of the shop.
# Run it with: uvicorn app:app

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import dubbo
from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig, ConsumerConfig, ReferenceConfig
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shop import REGISTRIES, Order, Orders, User, Users

# The Dubbo application and its references are created once, at import, and
# shared by every request. A request may take 2 seconds in all.
dubbo_app = Dubbo(
    application=ApplicationConfig(name="shop-gateway"),
    registries=REGISTRIES,
    consumer=ConsumerConfig(timeout=2),
)
users = dubbo_app.refer(Users)
# A call that failed as UNAVAILABLE is attempted again by default; an order
# must not be placed twice, so its calls are not.
orders = dubbo_app.refer(Orders, config=ReferenceConfig(retries=0))


# FastAPI enters the lifespan when the server starts and exits it when the
# server stops, in one task, as a Dubbo application must be entered and
# exited. Requests are served in between, while the Dubbo application runs.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with dubbo_app:
        yield


app = FastAPI(lifespan=lifespan)


# Every Dubbo call made for a request carries its trace id, which the
# services print, and the response tells it to the client.
@app.middleware("http")
async def trace(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex[:8]
    with dubbo.outgoing({"trace-id": trace_id}):
        response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


# A failed call answers with the HTTP status that matches its own; any
# other failure of a service is one of the gateway.
HTTP_STATUSES = {
    Status.INVALID_ARGUMENT: 400,
    Status.NOT_FOUND: 404,
    Status.FAILED_PRECONDITION: 409,
    Status.UNAVAILABLE: 503,
    Status.DEADLINE_EXCEEDED: 504,
}


@app.exception_handler(RpcError)
async def rpc_error(request: Request, error: RpcError) -> JSONResponse:
    return JSONResponse({"detail": error.message}, status_code=HTTP_STATUSES.get(error.status, 502))


class OrderRequest(BaseModel):
    user_id: int
    item: str
    quantity: int


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> User:
    return await users.get_user(user_id)


@app.post("/orders")
async def place_order(request: OrderRequest) -> Order:
    return await orders.place_order(request.user_id, request.item, request.quantity)
