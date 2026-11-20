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

# A provider of a user service, with a contract like any other. The consumer
# in client.py does not import it.

import asyncio
import typing

import dubbo
from dubbo import Dubbo, RpcError, Status
from dubbo.config import ApplicationConfig, ProtocolConfig

USERS = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
}


@dubbo.service("org.apache.dubbo.samples.Users")
class Users(typing.Protocol):
    async def get_user(self, user_id: int) -> dict[str, typing.Any]: ...

    async def find_names(self, prefix: str) -> list[str]: ...


class UsersImpl(Users):
    async def get_user(self, user_id: int) -> dict[str, typing.Any]:
        if user_id not in USERS:
            raise RpcError(Status.NOT_FOUND, f"no user has ID {user_id}")
        return USERS[user_id]

    async def find_names(self, prefix: str) -> list[str]:
        return [user["name"] for user in USERS.values() if user["name"].startswith(prefix)]


async def main() -> None:
    app = Dubbo(application=ApplicationConfig(name="generic-server"), protocols={"dubbo": ProtocolConfig(port=20880)})
    app.export(UsersImpl())

    async with app:
        print("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
