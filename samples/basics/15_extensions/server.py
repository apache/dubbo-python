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

# The provider: it reads its configuration from server.toml, which only the
# installed dubbo-toml plugin can read.

import asyncio
from pathlib import Path

from dubbo import Dubbo

from greeter import Greeter

HERE = Path(__file__).parent


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"


async def main() -> None:
    app = Dubbo(HERE / "server.toml")
    app.export(GreeterImpl())

    async with app:
        print(f"{app.config.application.name} serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
