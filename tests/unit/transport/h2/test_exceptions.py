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

from dubbo import DubboError
from dubbo.transport.h2 import (
    H2ConnectionError,
    H2Error,
    H2StreamError,
    H2StreamResetError,
)


def test_h2_connection_error_preserves_goaway_context() -> None:
    error = H2ConnectionError("peer rejected the connection", error_code=1, last_stream_id=7)

    assert isinstance(error, H2Error)
    assert isinstance(error, DubboError)
    assert error.error_code == 1
    assert error.last_stream_id == 7


def test_h2_stream_reset_preserves_unknown_error_code() -> None:
    error = H2StreamResetError(stream_id=3, error_code=0xFF)

    assert isinstance(error, H2StreamError)
    assert error.stream_id == 3
    assert error.error_code == 0xFF
