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
"""Check that an application serves and calls with only the default dependencies, as a fresh install has them.

Run with ``python scripts/check_install.py`` in an environment that holds the
default dependencies alone: it makes one call over each built-in protocol.
"""

import asyncio
import typing

import dubbo
from dubbo import Dubbo
from dubbo.config import ConsumerConfig, ProtocolConfig, ReferenceConfig

_APP = {"application": {"name": "check-install"}}


async def _call(protocol: str, port: int, echo: type, impl: object, value: object) -> None:
    provider = Dubbo(
        _APP, protocols={protocol: ProtocolConfig(name=protocol, host="127.0.0.1", port=port)}, env_prefix=None
    )
    provider.export(impl)
    reference = ReferenceConfig(urls=(f"{protocol}://127.0.0.1:{port}/check.Echo",))
    consumer = Dubbo(_APP, consumer=ConsumerConfig(references={"check.Echo": reference}), env_prefix=None)
    caller = consumer.refer(echo)

    async with provider, consumer:
        assert await caller.echo(value) == value


async def _tri() -> None:
    from google.protobuf.wrappers_pb2 import StringValue

    @dubbo.service("check.Echo")
    class Echo(typing.Protocol):
        async def echo(self, text: StringValue) -> StringValue: ...

    class EchoImpl(Echo):
        async def echo(self, text: StringValue) -> StringValue:
            return text

    await _call("tri", 50071, Echo, EchoImpl(), StringValue(value="hi"))


async def _hessian2() -> None:
    @dubbo.service("check.Echo")
    class Echo(typing.Protocol):
        async def echo(self, text: str) -> str: ...

    class EchoImpl(Echo):
        async def echo(self, text: str) -> str:
            return text

    await _call("dubbo", 50072, Echo, EchoImpl(), "hi")


async def _main() -> None:
    await _tri()
    await _hessian2()


if __name__ == "__main__":
    asyncio.run(_main())
