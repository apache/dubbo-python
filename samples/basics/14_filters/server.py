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

# The provider: every call it serves goes through the timing filter, then the
# API key check, before it reaches the Greeter.

import asyncio
import logging

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, ProviderConfig

import filters
from greeter import Greeter


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    filters.register()

    app = Dubbo(
        application=ApplicationConfig(name="filters-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
        provider=ProviderConfig(
            # The first filter is the outermost: timing measures the check too.
            filters=("timing", "api-key-check"),
            # Parameters reach the URL the filters are created with. Keep real
            # keys out of the code, in the environment or a secret store.
            parameters={"api-key": "s3cret"},
        ),
    )
    app.export(GreeterImpl())

    async with app:
        print("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
