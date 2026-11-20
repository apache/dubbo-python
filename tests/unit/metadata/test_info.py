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

import hashlib
import json

from dubbo.metadata import MetadataInfo, ServiceInfo


def test_the_revision_hashes_the_services_as_dubbo_for_java_describes_them():
    service = ServiceInfo(
        name="com.example.Greeter",
        group="g",
        version="1.0",
        protocol="tri",
        port=50051,
        path="com.example.Greeter",
        params={"side": "provider", "methods": "greet"},
    )
    info = MetadataInfo.from_services("demo", [service])

    # MetadataInfo#calRevision: the application, then per service its match
    # key, port, path and parameters as java.util.TreeMap#toString renders them.
    described = "g/com.example.Greeter:1.0:tri50051com.example.Greeter{methods=greet, side=provider}"

    assert service.describe() == described
    assert info.revision == hashlib.md5(("demo" + described).encode()).hexdigest()
    assert MetadataInfo.from_services("demo", []).revision == "0"


def test_remote_metadata_reads_back_from_its_json():
    service = ServiceInfo(
        name="com.example.Greeter", protocol="tri", port=50051, path="com.example.Greeter", params={"a": "1"}
    )
    info = MetadataInfo.from_services("demo", [service])

    data = json.loads(info.to_json())

    assert data == {
        "app": "demo",
        "revision": info.revision,
        "services": {
            "com.example.Greeter:tri": {
                "name": "com.example.Greeter",
                "protocol": "tri",
                "port": 50051,
                "path": "com.example.Greeter",
                "params": {"a": "1"},
            }
        },
    }
    assert MetadataInfo.from_json(info.to_json()) == info
