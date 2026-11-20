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

# The consumer: it calls the Greeter that server.py serves.

import asyncio

from dubbo import Dubbo

from greeter_dubbo import Greeter
from greeter_pb2 import HelloRequest


async def main() -> None:
    app = Dubbo()

    # Callers refer to the generated Greeter protocol, not to the servicer.
    greeter = app.refer(Greeter, url="tri://127.0.0.1:50051")

    async with app:
        reply = await greeter.say_hello(HelloRequest(name="Dubbo"))
        print(reply.message)


if __name__ == "__main__":
    asyncio.run(main())
