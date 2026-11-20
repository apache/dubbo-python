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

import os
import select
import ssl
import sys
import time
from pathlib import Path

import pytest

from dubbo.transport.tls import get_ssl_context
from dubbo.url import SSL_CONTEXT, URL

_CERTIFICATES = Path(__file__).resolve().parents[2] / "certificates"


_CERT_FILE = str(_CERTIFICATES / "localhost-cert.pem")


_KEY_FILE = str(_CERTIFICATES / "localhost-key.pem")


# The key of _KEY_FILE encrypted with the password "dubbo", by `openssl pkey -aes256`.
_ENCRYPTED_KEY_FILE = str(_CERTIFICATES / "localhost-key-encrypted.pem")


def test_get_ssl_context_returns_none_without_tls() -> None:
    assert get_ssl_context(URL.parse("tri://127.0.0.1:50051?ssl-enabled=false"), server=False) is None


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("ssl-enabled=maybe", "ssl-enabled.*bool"),
        (f"ca-cert-file={_CERT_FILE}", "need ssl-enabled=true"),
        (f"ssl-enabled=true&tls-key-file={_KEY_FILE}", "tls-cert-file"),
    ],
)
def test_get_ssl_context_rejects_inconsistent_parameters(query: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        get_ssl_context(URL.parse(f"tri://127.0.0.1:50051?{query}"), server=False)


def test_get_ssl_context_requires_a_server_certificate() -> None:
    with pytest.raises(ValueError, match="tls-cert-file"):
        get_ssl_context(URL.parse("tri://127.0.0.1:50051?ssl-enabled=true"), server=True)


def test_get_ssl_context_configures_tls_1_2_or_later() -> None:
    client = get_ssl_context(URL.parse("tri://127.0.0.1:50051?ssl-enabled=true"), server=False)
    server = get_ssl_context(
        URL.parse(f"tri://127.0.0.1:50051?ssl-enabled=true&tls-cert-file={_CERT_FILE}&tls-key-file={_KEY_FILE}"),
        server=True,
    )

    assert client is not None
    assert server is not None
    assert client.verify_mode == ssl.CERT_REQUIRED
    assert client.check_hostname
    assert server.verify_mode == ssl.CERT_NONE
    for context in (client, server):
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
        assert context.options & ssl.OP_NO_COMPRESSION
        assert context.options & ssl.OP_NO_RENEGOTIATION


def test_get_ssl_context_lets_a_server_require_client_certificates() -> None:
    url = URL.parse(
        f"tri://127.0.0.1:50051?ssl-enabled=true&tls-cert-file={_CERT_FILE}"
        f"&tls-key-file={_KEY_FILE}&ca-cert-file={_CERT_FILE}"
    )

    context = get_ssl_context(url, server=True)

    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_get_ssl_context_returns_a_given_context_as_it_is() -> None:
    given = ssl.create_default_context()
    url = URL.parse(f"tri://127.0.0.1:50051?ssl-enabled=true&ca-cert-file={_CERT_FILE}").replace(
        attributes={SSL_CONTEXT: given}
    )

    assert get_ssl_context(url, server=False) is given
    assert given.minimum_version == ssl.create_default_context().minimum_version


def test_get_ssl_context_rejects_a_context_for_the_other_side_or_without_tls() -> None:
    client = URL.parse("tri://127.0.0.1:50051?ssl-enabled=true").replace(
        attributes={SSL_CONTEXT: ssl.create_default_context()}
    )
    with pytest.raises(ValueError, match="PROTOCOL_TLS_CLIENT"):
        get_ssl_context(client, server=True)

    cleartext = URL.parse("tri://127.0.0.1:50051").replace(attributes={SSL_CONTEXT: ssl.create_default_context()})
    with pytest.raises(ValueError, match="need ssl-enabled=true"):
        get_ssl_context(cleartext, server=False)


@pytest.mark.skipif(sys.platform == "win32", reason="needs a pseudo-terminal")
def test_get_ssl_context_fails_an_encrypted_key_without_prompting_on_a_terminal() -> None:
    code = (
        "from dubbo.transport.tls import get_ssl_context; from dubbo.url import URL\n"
        "try:\n"
        f"    get_ssl_context(URL.parse('tri://127.0.0.1:0?ssl-enabled=true&tls-cert-file={_CERT_FILE}"
        f"&tls-key-file={_ENCRYPTED_KEY_FILE}'), server=True)\n"
        "except OSError as error:\n"
        "    print(type(error).__name__)\n"
    )
    import pty  # It imports termios, which Windows lacks.

    pid, terminal = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c", code])

    output = b""
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline and b"\n" not in output:
            if select.select([terminal], [], [], 0.05)[0]:
                output += os.read(terminal, 1024)
    finally:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        os.close(terminal)

    assert output.strip() == b"SSLError"
