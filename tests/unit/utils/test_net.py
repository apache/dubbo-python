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

import socket
from types import SimpleNamespace

import psutil
import pytest

from dubbo.utils.net import local_host, match_address


def _interfaces(monkeypatch, interfaces, host_name_address="127.0.1.1"):
    """Make the machine have ``interfaces``, by name its state and addresses, and resolve its host name to ``host_name_address``."""
    monkeypatch.setattr(
        psutil,
        "net_if_addrs",
        lambda: {
            name: [SimpleNamespace(family=family, address=address) for family, address in addresses]
            for name, (_, addresses) in interfaces.items()
        },
    )
    monkeypatch.setattr(
        psutil, "net_if_stats", lambda: {name: SimpleNamespace(isup=up) for name, (up, _) in interfaces.items()}
    )
    monkeypatch.setattr(socket, "gethostbyname", lambda name: host_name_address)


def test_without_targets_the_local_host_is_a_private_ipv4_address_of_an_interface_that_is_up(monkeypatch) -> None:
    _interfaces(
        monkeypatch,
        {
            "lo": (True, [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")]),
            "eth0": (False, [(socket.AF_INET, "10.0.0.9")]),
            "eth1": (
                True,
                [(socket.AF_INET, "169.254.1.1"), (socket.AF_INET, "203.0.113.5"), (socket.AF_INET, "192.168.1.7")],
            ),
        },
    )

    assert local_host([]) == "192.168.1.7"


@pytest.mark.parametrize(
    ("addresses", "expected"),
    [
        ([(socket.AF_INET6, "2001:db8::5"), (socket.AF_INET, "203.0.113.5")], "203.0.113.5"),
        ([(socket.AF_INET6, "fe80::1"), (socket.AF_INET6, "2001:db8::5")], "2001:db8::5"),
    ],
    ids=["public-ipv4", "ipv6"],
)
def test_without_a_private_ipv4_address_an_ipv4_address_comes_before_an_ipv6_one(
    monkeypatch, addresses, expected
) -> None:
    _interfaces(monkeypatch, {"eth0": (True, addresses)})

    assert local_host([]) == expected


@pytest.mark.parametrize(("host_name_address", "expected"), [("127.0.1.1", "127.0.0.1"), ("10.1.2.3", "10.1.2.3")])
def test_without_an_interface_address_the_host_name_gives_an_address_that_is_not_a_loopback(
    monkeypatch, host_name_address, expected
) -> None:
    _interfaces(monkeypatch, {"lo": (True, [(socket.AF_INET, "127.0.0.1")])}, host_name_address)

    assert local_host([]) == expected


@pytest.mark.parametrize("loopback", ["127.0.0.1", "::1"])
def test_the_local_host_is_the_address_that_reaches_the_target(loopback: str) -> None:
    assert local_host([("unresolvable.invalid", 2181), (loopback, None)]) == loopback


@pytest.mark.parametrize(
    ("pattern", "host", "port", "matches"),
    [
        ("*", "10.0.0.1", 1, True),
        ("10.0.0.1", "10.0.0.1", 1, True),
        ("10.0.0.1:2", "10.0.0.1", 1, False),
        ("10.0.*.1-5", "10.0.9.3", 1, True),
        ("10.0.*.1-5", "10.0.9.6", 1, False),
        ("10.0.0.0/8", "10.9.9.9", 1, True),
        ("*.*.*.*:7", "10.0.0.1", 7, True),
        ("[fe80::1]:7", "fe80::1", 7, True),
        ("fe80:0:0:0:0:0:0:*", "fe80::abcd", 7, True),
        ("fe80:0:0:0:0:0:0:1-f", "fe80::abcd", 7, False),
    ],
    ids=[
        "any-address",
        "exact-ipv4",
        "different-port",
        "ipv4-range-matches",
        "ipv4-range-misses",
        "ipv4-cidr",
        "wildcard-with-port",
        "ipv6-with-port",
        "ipv6-wildcard",
        "ipv6-range-misses",
    ],
)
def test_an_address_pattern_matches_by_ip_expression(pattern: str, host: str, port: int, matches: bool) -> None:
    assert match_address(pattern, host, port) is matches


def test_an_ipv4_pattern_needs_four_parts() -> None:
    with pytest.raises(ValueError, match="not an IPv4 pattern"):
        match_address("10.0.*", "10.0.0.1", 1)


@pytest.mark.parametrize(
    ("pattern", "host"),
    [("10.0.0.x-1", "10.0.0.1"), ("1.2.3.4", "h")],
    ids=["invalid-ipv4-range", "non-ip-host"],
)
def test_a_malformed_pattern_or_host_raises(pattern: str, host: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - the standard library words these
        match_address(pattern, host, 1)
