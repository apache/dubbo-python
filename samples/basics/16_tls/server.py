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

# The provider: it serves the Greeter over TLS, and accepts only clients with
# a certificate that the sample's authority signed.

import asyncio
from pathlib import Path

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig, TLSConfig, TripleConfig

from greeter_dubbo import GreeterServicer
from greeter_pb2 import HelloReply, HelloRequest

CERTS = Path(__file__).parent / "certs"


class GreeterImpl(GreeterServicer):
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        return HelloReply(message=f"Hello, {request.name}, over TLS!")


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="tls-server"),
        # Replies are compressed with gzip for the callers that accept it.
        protocols={"tri": ProtocolConfig(port=50051, triple=TripleConfig(compressor="gzip"))},
        tls=TLSConfig(
            # The certificate the server presents, with its private key.
            certfile=CERTS / "server.pem",
            # Setting the authority on a server requires every client to
            # present a certificate it signed: mutual TLS.
            cafile=CERTS / "ca.pem",
        ),
    )
    app.export(GreeterImpl())

    async with app:
        print("Serving over TLS on port 50051; press Ctrl+C to stop")
        await app.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
