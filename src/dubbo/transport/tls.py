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

"""TLS for the transports, configured by the parameters of a URL."""

import ssl
from collections.abc import Sequence

from dubbo.constants import (
    CA_CERT_FILE_KEY,
    SSL_ENABLED_KEY,
    TLS_CERT_FILE_KEY,
    TLS_KEY_FILE_KEY,
    TLS_SERVER_NAME_KEY,
)
from dubbo.url import SSL_CONTEXT, URL
from dubbo.utils.converters import boolean, milliseconds

__all__ = ["TLS_KEYS", "get_ssl_context", "server_hostname", "ssl_handshake_timeout"]

_SSL_HANDSHAKE_TIMEOUT_KEY = "ssl-handshake-timeout"
_DEFAULT_SSL_HANDSHAKE_TIMEOUT = 10.0  # Seconds.

# The URL parameters that configure TLS.
TLS_KEYS = (SSL_ENABLED_KEY, CA_CERT_FILE_KEY, TLS_CERT_FILE_KEY, TLS_KEY_FILE_KEY, TLS_SERVER_NAME_KEY)


def get_ssl_context(url: URL, *, server: bool, alpn: Sequence[str] = ()) -> ssl.SSLContext | None:
    """Return the TLS context of the server or client of ``url``, or ``None`` for cleartext.

    ``ssl-enabled=true`` enables TLS. The ``ssl.SSLContext`` in the
    attributes of ``url``, if any, is returned as it is. Otherwise a new
    context enables TLS 1.2 or later without compression, offers the
    protocols of ``alpn`` through ALPN, and takes PEM file paths and a name:

    - A client trusts ``ca-cert-file``, or the system certificates when it is
      absent, checks that the server certificate carries the name
      `server_hostname` returns, and presents ``tls-cert-file`` when the
      server asks for a client certificate.
    - A server presents ``tls-cert-file``, which it requires, and with
      ``ca-cert-file`` requires each client to present a certificate it
      trusts.

    ``tls-key-file`` holds the private key of ``tls-cert-file``; it may be
    omitted when the certificate file holds the key too. An encrypted key
    fails with `ssl.SSLError`.

    Raises:
        ValueError: ``ssl-enabled`` is not a boolean, a TLS parameter or
            context is set without enabling TLS, a certificate is missing,
            or the context is made for the other side.
        OSError: A file cannot be read, or holds no valid certificate or key.
    """
    parameters = url.parameters
    context = url.attributes.get(SSL_CONTEXT)
    if not url.get_parameter(SSL_ENABLED_KEY, boolean, False):
        configured = [key for key in TLS_KEYS[1:] if key in parameters]
        if context is not None:
            configured.append("the TLS context")
        if configured:
            raise ValueError(f"{configured} need {SSL_ENABLED_KEY}=true")
        return None

    if isinstance(context, ssl.SSLContext):
        other = ssl.PROTOCOL_TLS_CLIENT if server else ssl.PROTOCOL_TLS_SERVER
        if context.protocol == other:
            raise ValueError(f"a {'server' if server else 'client'} cannot use a TLS context made with {other.name}")
        return context

    ca_file = parameters.get(CA_CERT_FILE_KEY)
    cert_file = parameters.get(TLS_CERT_FILE_KEY)
    key_file = parameters.get(TLS_KEY_FILE_KEY)
    if cert_file is None and (server or key_file is not None):
        raise ValueError(f"URL parameter {TLS_CERT_FILE_KEY!r} is required by a server and by {TLS_KEY_FILE_KEY!r}")

    if server:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if ca_file is not None:
            context.load_verify_locations(ca_file)
            context.verify_mode = ssl.CERT_REQUIRED
    else:
        context = ssl.create_default_context(cafile=ca_file)
    if cert_file is not None:
        # With an empty password, an encrypted key fails at once, with no prompt on the terminal.
        context.load_cert_chain(cert_file, key_file, password="")

    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION | ssl.OP_NO_RENEGOTIATION
    if alpn:
        context.set_alpn_protocols(list(alpn))

    return context


def server_hostname(url: URL) -> str | None:
    """Return the name a client checks the server certificate for: ``tls-server-name``, or the URL host when it is absent or empty."""
    return url.parameters.get(TLS_SERVER_NAME_KEY) or url.host


def ssl_handshake_timeout(url: URL) -> float:
    """Return the seconds a server of ``url`` gives each TLS handshake: ``ssl-handshake-timeout``, whole milliseconds, 10000 when absent.

    Raises:
        ValueError: The timeout is not positive whole milliseconds.
    """
    timeout = url.get_parameter(_SSL_HANDSHAKE_TIMEOUT_KEY, milliseconds, _DEFAULT_SSL_HANDSHAKE_TIMEOUT)
    if not timeout > 0:
        raise ValueError(f"URL parameter {_SSL_HANDSHAKE_TIMEOUT_KEY!r} must be positive")
    return timeout
