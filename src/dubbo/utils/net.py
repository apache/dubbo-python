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

import ipaddress
import socket
from collections.abc import Iterable

import psutil

__all__ = ["format_address", "local_host", "match_address", "split_address"]

# Any port picks the route; nothing is sent to it.
_DISCARD_PORT = 9
# The private IPv4 networks of RFC 1918.
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def format_address(host: str, port: int | str | None) -> str:
    """Return ``host`` and ``port``, if any, as ``host:port``, an IPv6 host in brackets."""
    host = f"[{host}]" if ":" in host else host
    return host if port is None else f"{host}:{port}"


def split_address(address: str) -> tuple[str, str | None]:
    """Split ``host:port`` or ``[host]:port`` into the host and the port, if any; an IPv6 host without brackets has none."""
    if address.startswith("["):
        host, _, rest = address[1:].partition("]")
        return host, rest.removeprefix(":") or None
    if address.count(":") == 1:
        host, _, port = address.partition(":")
        return host, port
    return address, None


def local_host(targets: Iterable[tuple[str, int | None]]) -> str:
    """Return the local IP address of the route to the first of ``targets``, ``(host, port)`` pairs, that can be reached.

    IPv4 and IPv6 targets both work. When none can be reached, it returns an
    address of an interface that is up, a private IPv4 one first, then
    another IPv4 one, then an IPv6 one, else the address of the host name,
    and else ``127.0.0.1``; none of these is a loopback or a link-local
    address. It blocks on name resolution, so async callers run it in a
    thread.
    """
    for host, port in targets:
        try:
            infos = socket.getaddrinfo(host, port or _DISCARD_PORT, type=socket.SOCK_DGRAM)
        except OSError:
            continue
        for family, kind, proto, _, address in infos:
            try:
                # Connecting a UDP socket sends nothing; it only picks the route.
                with socket.socket(family, kind, proto) as udp:
                    udp.connect(address)
                    return udp.getsockname()[0]
            except OSError:
                continue

    return _interface_address() or _host_name_address() or "127.0.0.1"


def match_address(pattern: str, host: str | None, port: int | None) -> bool:
    """Return whether the address at ``host`` and ``port`` matches ``pattern``, as tag rules list providers.

    ``pattern`` is ``*``, a CIDR block, an IP address, or an IP address whose
    segments are ``*`` or a range such as ``1-9``, with an optional port
    after ``:``, or ``]:`` for IPv6. Host names are not resolved.

    Raises:
        ValueError: ``pattern`` is malformed or of another IP version than
            ``host``, or ``host`` is not an IP address.
    """
    if pattern in ("*", "*.*.*.*"):
        return True
    if "/" in pattern:
        return ipaddress.ip_address(host) in ipaddress.ip_network(pattern, strict=False)  # ty: ignore[invalid-argument-type]

    address = ipaddress.ip_address(host)  # ty: ignore[invalid-argument-type]
    ipv4 = address.version == 4
    pattern_port = None
    if pattern.startswith("["):
        pattern, _, rest = pattern[1:].partition("]")
        pattern_port = rest.removeprefix(":") or None
    elif ipv4 and ":" in pattern:
        pattern, _, pattern_port = pattern.partition(":")
    if pattern_port is not None and pattern_port != str(port or 0):
        return False

    if "*" not in pattern and "-" not in pattern:
        return ipaddress.ip_address(pattern) == address

    masks = pattern.split("." if ipv4 else ":")
    values = str(address).split(".") if ipv4 else [f"{int(group, 16):x}" for group in address.exploded.split(":")]
    if len(masks) != len(values):
        raise ValueError(f"{pattern!r} is not an IPv{address.version} pattern")

    base = 10 if ipv4 else 16
    for mask, value in zip(masks, values, strict=True):
        if mask == "*":
            continue
        low, _, high = mask.partition("-")
        if not int(low, base) <= int(value, base) <= int(high or low, base):
            return False
    return True


def _interface_address() -> str | None:
    """Return the best address of an interface that is up, a private IPv4 one first, then another IPv4 one, then IPv6."""
    stats = psutil.net_if_stats()
    candidates = [
        ip
        for name, addresses in psutil.net_if_addrs().items()
        if (stat := stats.get(name)) is not None and stat.isup
        for address in addresses
        if address.family in (socket.AF_INET, socket.AF_INET6)
        and _is_reachable(ip := ipaddress.ip_address(address.address.partition("%")[0]))
    ]

    best = min(candidates, key=_preference, default=None)
    return None if best is None else str(best)


def _host_name_address() -> str | None:
    """Return the address the host name resolves to, unless it is a loopback one, as ``/etc/hosts`` often maps it."""
    try:
        address = ipaddress.ip_address(socket.gethostbyname(socket.gethostname()))
    except (OSError, ValueError):
        return None

    return str(address) if _is_reachable(address) else None


def _is_reachable(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether another host may reach ``address``: not a loopback, link-local or unspecified one."""
    return not (address.is_loopback or address.is_link_local or address.is_unspecified)


def _preference(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> int:
    """Rank ``address``: a private IPv4 one first, then another IPv4 one, then IPv6."""
    if address.version == 6:
        return 2

    return 0 if any(address in network for network in _PRIVATE_NETWORKS) else 1
