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

import json

import pytest

from dubbo.metadata.instance import InstanceMetadata
from dubbo.url import URL

_V1 = "org.apache.dubbo.metadata.MetadataService"
_V2 = "org.apache.dubbo.metadata.MetadataServiceV2"


def _metadata(params: object, **values: str) -> dict[str, str]:
    return {"dubbo.metadata.revision": "r1", "dubbo.metadata-service.url-params": json.dumps(params), **values}


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        pytest.param(
            _metadata({"protocol": "tri", "port": "50052", "version": "2.0.0"}, **{"meta-v": "2.0.0"}),
            URL(protocol="tri", host="10.0.0.1", port=50052, path=_V2, parameters={"version": "2.0.0"}),
            id="v2-over-tri",
        ),
        pytest.param(
            _metadata({"protocol": "dubbo", "port": "20880", "version": "1.0.0"}, **{"meta-v": "1.0.0"}),
            URL(
                protocol="dubbo",
                host="10.0.0.1",
                port=20880,
                path=_V1,
                parameters={"version": "1.0.0", "serialization": "hessian2"},
            ),
            id="v1-over-dubbo",
        ),
        pytest.param(
            _metadata({"protocol": "tri", "port": "50052"}),
            URL(
                protocol="tri",
                host="10.0.0.1",
                port=50052,
                path=_V1,
                parameters={"version": "1.0.0", "serialization": "hessian2"},
            ),
            id="v1-over-tri-without-meta-v",
        ),
        pytest.param(
            _metadata({"protocol": "dubbo"}, **{"meta-v": "2.0.0"}),
            URL(
                protocol="dubbo",
                host="10.0.0.1",
                port=50051,
                path=_V1,
                parameters={"version": "1.0.0", "serialization": "hessian2"},
            ),
            id="v1-at-the-instance-port-over-a-protocol-other-than-tri",
        ),
    ],
)
def test_local_metadata_locates_the_metadata_service_it_says(metadata: dict[str, str], expected: URL) -> None:
    instance = InstanceMetadata.from_metadata("10.0.0.1", 50051, metadata)

    assert instance is not None
    assert instance.metadata_service == expected


def test_an_instance_without_metadata_service_parameters_serves_none() -> None:
    instance = InstanceMetadata.from_metadata("10.0.0.1", 50051, {"dubbo.metadata.revision": "r1"})

    assert instance is not None
    assert instance.metadata_service is None


def test_remote_metadata_is_not_read_from_the_instance() -> None:
    metadata = _metadata({"protocol": "tri"}, **{"dubbo.metadata.storage-type": "remote"})

    instance = InstanceMetadata.from_metadata("10.0.0.1", 50051, metadata)

    assert instance is not None
    assert instance.metadata_service is None


@pytest.mark.parametrize(
    "params", [pytest.param([], id="not-an-object"), pytest.param({"port": "1"}, id="no-protocol")]
)
def test_metadata_service_parameters_that_cannot_be_read_fail(params: object) -> None:
    with pytest.raises(ValueError, match="cannot be read"):
        InstanceMetadata.from_metadata("10.0.0.1", 50051, _metadata(params))
