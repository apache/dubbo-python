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

import subprocess
import sys


def test_h2_contract_import_does_not_load_aio_plugin() -> None:
    script = """
import sys
import dubbo.transport.h2 as h2
from typing import get_type_hints

assert "ngh2" not in sys.modules
assert "dubbo.transport.h2.aio" not in sys.modules
assert not hasattr(h2, "AioH2Client")
get_type_hints(h2.H2Client.open_stream)
assert "ngh2" not in sys.modules
assert "dubbo.transport.h2.aio" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True)
