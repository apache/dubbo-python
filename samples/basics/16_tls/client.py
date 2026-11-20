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

# The consumer: it calls the Greeter over TLS, once with its certificate, and
# once without.

import asyncio
from pathlib import Path

from dubbo import Dubbo, RpcError
from dubbo.config import ConsumerConfig, TLSConfig, TripleConfig

from greeter_dubbo import Greeter
from greeter_pb2 import HelloRequest

CERTS = Path(__file__).parent / "certs"


async def greet(tls: TLSConfig) -> str:
    app = Dubbo(
        tls=tls,
        # Requests are compressed with gzip too.
        consumer=ConsumerConfig(triple=TripleConfig(compressor="gzip"), check=False),
    )
    # With TLS configured, every connection of the application uses it.
    greeter = app.refer(Greeter, url="tri://localhost:50051")
    async with app:
        try:
            reply = await greeter.say_hello(HelloRequest(name="Alice"))
        except RpcError as error:
            return f"{error.status.name}: {error.message}"
        return reply.message


async def main() -> None:
    # The client trusts the sample's authority, which signed the server
    # certificate, and presents its own certificate when the server asks.
    with_certificate = TLSConfig(cafile=CERTS / "ca.pem", certfile=CERTS / "client.pem")
    print("With a client certificate:", await greet(with_certificate))

    # Without its certificate, the server refuses the connection.
    print("Without:", await greet(TLSConfig(cafile=CERTS / "ca.pem")))


if __name__ == "__main__":
    asyncio.run(main())
