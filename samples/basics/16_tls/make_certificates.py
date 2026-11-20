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

# Makes a certificate authority for testing, and certificates it signs for the
# server and the client, in certs/. Real deployments get them from their own
# authority instead. Needs trustme: pip install trustme

from pathlib import Path

import trustme

CERTS = Path(__file__).parent / "certs"


def main() -> None:
    CERTS.mkdir(exist_ok=True)
    authority = trustme.CA()
    authority.cert_pem.write_to_path(CERTS / "ca.pem")

    # The server certificate names the host clients connect to.
    server = authority.issue_cert("localhost", "127.0.0.1")
    server.private_key_and_cert_chain_pem.write_to_path(CERTS / "server.pem")

    # The client certificate identifies the client to servers that ask.
    client = authority.issue_cert("greeter-client")
    client.private_key_and_cert_chain_pem.write_to_path(CERTS / "client.pem")

    print(f"Wrote ca.pem, server.pem and client.pem to {CERTS}")


if __name__ == "__main__":
    main()
