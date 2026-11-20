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

# The consumer: it handles each way a call fails.

import asyncio

import anyio
from dubbo import Dubbo, RpcError, Status
from dubbo.config import MethodConfig, ReferenceConfig

from users_dubbo import Users
from users_pb2 import ExportUsersRequest, GetUserRequest


async def main() -> None:
    # A call may take 1 second by default. ExportUsers is known to be slow,
    # so the reference gives it 5 seconds, by the name of the method in the
    # proto file.
    app = Dubbo()
    users = app.refer(
        Users,
        url="tri://127.0.0.1:50051",
        config=ReferenceConfig(methods={"ExportUsers": MethodConfig(timeout=5)}),
    )

    async with app:
        # The provider rejects every other attempt as UNAVAILABLE, and the
        # failover cluster attempts the call again, up to 2 more times by
        # default, so these calls succeed.
        for user_id in [1, 2]:
            user = await users.get_user(GetUserRequest(id=user_id))
            print(f"User {user.id}: {user.name}")

        # Other statuses are not attempted again: they reach the caller as
        # RpcError, whose status says what went wrong.
        for user_id in [42, -1]:
            try:
                await users.get_user(GetUserRequest(id=user_id))
            except RpcError as error:
                if error.status == Status.NOT_FOUND:
                    print(f"No user {user_id}")
                else:
                    print(f"Failed: {error.status.name}: {error.message}")

        # Within its 5 seconds, the slow call succeeds.
        reply = await users.export_users(ExportUsersRequest())
        print(f"Exported {reply.count} users")

        # anyio.fail_after() bounds the calls in its block further. Over Triple
        # its deadline travels with the call, so the provider stops working on
        # a call that its caller has given up on.
        try:
            with anyio.fail_after(1):
                await users.export_users(ExportUsersRequest())
        except TimeoutError:
            print("Gave up exporting after 1 second")


if __name__ == "__main__":
    asyncio.run(main())
