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

import pytest


@pytest.mark.parametrize(
    "modules",
    [
        "dubbo.extension, dubbo.config, dubbo",
        "dubbo.config_center, dubbo",
        "dubbo.transport.zookeeper, dubbo",
        "dubbo.config, dubbo",
        "dubbo",
    ],
)
def test_packages_import_in_any_order(modules):
    result = subprocess.run([sys.executable, "-c", f"import {modules}"], capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, result.stderr
