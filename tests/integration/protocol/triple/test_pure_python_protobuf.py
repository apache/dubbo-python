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
import subprocess
import sys

_ROUND_TRIP = """
from google.protobuf.wrappers_pb2 import StringValue
from dubbo import Status
from dubbo.protocol.triple import ErrorDetail, TripleError
from dubbo.protocol.triple.grpc.status import status_headers, trailer_error

detail = ErrorDetail.from_message(StringValue(value="name"))
error = trailer_error(dict(status_headers(TripleError(Status.INVALID_ARGUMENT, "bad", details=[detail]))))
assert error.details == (detail,), error
"""


def test_error_details_travel_with_the_pure_python_protobuf_runtime():
    # Free-threaded builds of Python have only this runtime.
    environment = {**os.environ, "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python"}

    result = subprocess.run(
        [sys.executable, "-c", _ROUND_TRIP], capture_output=True, text=True, timeout=10, env=environment
    )

    assert result.returncode == 0, result.stderr
