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

# A consumer without the contract of the service it calls: it names the
# service and its methods as text, and passes and receives plain data. Such
# calls suit tools that call any service, such as gateways, consoles and
# tests.

import asyncio

from dubbo import Dubbo, RpcError


async def main() -> None:
    app = Dubbo()

    # refer_generic() takes the name of a service instead of its contract.
    users = app.refer_generic("org.apache.dubbo.samples.Users", url="dubbo://127.0.0.1:20880")

    async with app:
        # call() takes the name of a method and its arguments in order.
        print(await users.call("get_user", 1))
        print(await users.call("find_names", "A"))

        # Failures arrive as they do for any call.
        try:
            await users.call("get_user", 42)
        except RpcError as error:
            print(f"{error.status.name}: {error.message}")


if __name__ == "__main__":
    asyncio.run(main())
