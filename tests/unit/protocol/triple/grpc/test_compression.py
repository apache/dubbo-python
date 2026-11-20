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

import pytest

from dubbo.protocol.triple.grpc.compression import Compressors
from dubbo.url import URL

pytestmark = pytest.mark.anyio


def test_compressors_accept_identity_and_every_installed_compressor() -> None:
    compressors = Compressors(URL(protocol="tri"))

    assert compressors.accept_encoding == b"identity,bzip2,deflate,gzip"
    assert compressors.get(None) is None
    assert compressors.get(b"identity") is None
    assert compressors.get(b"gzip") is compressors.get(b"gzip")
    with pytest.raises(LookupError, match="not supported"):
        compressors.get(b"snappy")
