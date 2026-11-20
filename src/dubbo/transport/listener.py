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

"""The asyncio listeners that servers accept connections on."""

import asyncio
import ssl
from collections.abc import Callable
from typing import cast

__all__ = ["abort_handshakes", "create_listener"]

_SEVERAL_PORTS = "the host has several addresses, which port 0 binds to different ports; use an IP address or a port"


async def create_listener(
    create_connection: Callable[[], asyncio.BaseProtocol],
    host: str,
    port: int,
    ssl_context: ssl.SSLContext | None,
    ssl_handshake_timeout: float,
) -> tuple[asyncio.Server, tuple[str, int]]:
    """Return a listener on ``host`` and ``port`` that does not serve yet, which the caller closes, and the address it is bound to.

    Raises:
        OSError: The address cannot be bound.
        ValueError: A host name with port 0 would listen on several ports,
            one per address.
    """
    listener = await asyncio.get_running_loop().create_server(
        create_connection,
        host,
        port,
        ssl=ssl_context,
        ssl_handshake_timeout=ssl_handshake_timeout if ssl_context is not None else None,
        start_serving=False,
    )

    addresses = [listening.getsockname() for listening in listener.sockets]
    if len({address[1] for address in addresses}) > 1:
        listener.close()
        await listener.wait_closed()
        raise ValueError(_SEVERAL_PORTS)
    return listener, (cast(str, addresses[0][0]), cast(int, addresses[0][1]))


def abort_handshakes(listener: asyncio.Server) -> None:
    """Abort the transports of ``listener`` still in a TLS handshake, which never became connections and which closing it waits for."""
    # shortcut: CPython before 3.13 and uvloop have no abort_clients, so there a handshake under way outlives the
    # close by up to the handshake timeout; abort those transports directly if that ever matters.
    abort_clients = getattr(listener, "abort_clients", None)
    if abort_clients is not None:
        abort_clients()
