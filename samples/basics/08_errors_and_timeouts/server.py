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

# The provider: it fails calls on purpose, in the ways a real service does.

import asyncio

from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig

from users_dubbo import UsersServicer
from users_pb2 import ExportUsersReply, ExportUsersRequest, GetUserRequest, User

USERS = {1: "Alice", 2: "Bob"}


class UsersImpl(UsersServicer):
    def __init__(self) -> None:
        self.calls = 0

    async def get_user(self, request: GetUserRequest) -> User:
        # Every other call finds the service too busy. UNAVAILABLE tells the
        # caller that another attempt, maybe on another provider, may work.
        self.calls += 1
        if self.calls % 2 == 1:
            print(f"Rejecting call {self.calls}: too busy")
            raise RpcError(Status.UNAVAILABLE, "too busy, try again")

        # Raising RpcError fails the call with that status and message; the
        # caller receives an RpcError of the same status.
        if request.id < 0:
            raise RpcError(Status.INVALID_ARGUMENT, f"a user ID is not negative: {request.id}")
        if request.id not in USERS:
            raise RpcError(Status.NOT_FOUND, f"no user has ID {request.id}")
        return User(id=request.id, name=USERS[request.id])

    async def export_users(self, request: ExportUsersRequest) -> ExportUsersReply:
        await asyncio.sleep(3)
        return ExportUsersReply(count=len(USERS))


async def main() -> None:
    app = Dubbo(application=ApplicationConfig(name="errors-server"))
    app.export(UsersImpl())

    async with app:
        print("Serving on port 50051; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
