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

from pathlib import Path

import pytest

_CERTIFICATES = Path(__file__).resolve().parents[4] / "certificates"


_SERVER_TLS = {
    "ssl_enabled": "true",
    "tls_cert_file": str(_CERTIFICATES / "localhost-cert.pem"),
    "tls_key_file": str(_CERTIFICATES / "localhost-key.pem"),
}


_CLIENT_TLS = {"ssl_enabled": "true", "ca_cert_file": str(_CERTIFICATES / "localhost-cert.pem")}


@pytest.fixture
def server_tls():
    return _SERVER_TLS


@pytest.fixture
def client_tls():
    return _CLIENT_TLS


@pytest.fixture
def certificates():
    return _CERTIFICATES


@pytest.fixture
def path_headers(request_headers):
    """Return a function that gives the request headers with another ``:path``."""

    def path_headers(path: bytes) -> tuple[tuple[bytes, bytes], ...]:
        return tuple((name, path if name == b":path" else value) for name, value in request_headers)

    return path_headers
