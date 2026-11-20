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

# The provider: it logs each greeting, and Dubbo logs each call it serves.

import argparse
import asyncio
import logging

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, ProviderConfig

import logs
from greeter import Greeter

logger = logging.getLogger("greeter")


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        # extra= gives the record fields of its own, as Dubbo gives those of
        # each call to the records of its access log.
        logger.info("Greeting %s", name, extra={"user": name})
        return f"Hello, {name}!"


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="logging-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
        # accesslog logs each call that the services serve, at INFO to the
        # dubbo.accesslog logger.
        provider=ProviderConfig(accesslog=True),
    )
    app.export(GreeterImpl())

    async with app:
        logger.info("Serving on port 20880; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--structlog", action="store_true", help="render the lines with structlog")
    if parser.parse_args().structlog:
        import structlog_logs

        formatter = structlog_logs.formatter()
    else:
        formatter = logs.JsonFormatter()

    listener = logs.configure(formatter)
    try:
        asyncio.run(main())
    finally:
        # Writes what the queue still holds.
        listener.stop()
