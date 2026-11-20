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

# The provider: its service opens a database when the application starts,
# and on Ctrl+C lets the running calls finish before it closes the database.

import asyncio
from types import TracebackType
from typing import Self

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, ShutdownConfig

from greeter import Greeter


class Database:
    """Stands for a resource that the service uses, such as a connection pool."""

    @classmethod
    async def connect(cls) -> "Database":
        print("Database opened")
        return cls()

    async def close(self) -> None:
        print("Database closed")

    async def find_title(self, name: str) -> str:
        await asyncio.sleep(5)  # A slow query.
        return "Dr." if name == "Watson" else "Mx."


class GreeterImpl(Greeter):
    """A service that holds a database, opened and closed as an async context manager."""

    async def __aenter__(self) -> Self:
        self.database = await Database.connect()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.database.close()

    async def greet(self, name: str) -> str:
        print(f"Greeting {name}...")
        title = await self.database.find_title(name)
        print(f"Greeted {name}")
        return f"Hello, {title} {name}!"


async def main() -> None:
    greeter = GreeterImpl()

    # lifespan returns an async context manager, here the service itself. The
    # application enters it once it is ready and before the services serve,
    # and exits it after they have stopped serving, so the database is open
    # for every call.
    app = Dubbo(
        application=ApplicationConfig(name="graceful-shutdown-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
        # Stopping may take 15 seconds in all; what still runs then is cancelled.
        shutdown=ShutdownConfig(grace=15),
        lifespan=lambda app: greeter,
    )
    app.export(greeter)

    async with app:
        print("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()
        # Ctrl+C or SIGTERM ends serve_forever(). Leaving the block then stops
        # the application: it takes no new calls, waits for the running ones,
        # and exits the lifespan. A second Ctrl+C stops at once.
        print("Stopping; running calls finish first")
    print("Stopped")


if __name__ == "__main__":
    asyncio.run(main())
