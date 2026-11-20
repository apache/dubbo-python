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


def test_optional_import_helper_preserves_transitive_import_failures():
    from dubbo.utils import require_optional_dependency

    failure = ModuleNotFoundError("missing transitive dependency", name="dependency_internal")
    with (
        pytest.raises(ModuleNotFoundError, match="transitive") as caught,
        require_optional_dependency("yaml", extra="yaml"),
    ):
        raise failure
    assert caught.value is failure


@pytest.mark.parametrize("missing", ["google", "google.protobuf"])
def test_optional_import_helper_reports_a_missing_parent_package(missing):
    from dubbo.utils import require_optional_dependency

    with (
        pytest.raises(ModuleNotFoundError, match=r"apache-dubbo\[protobuf\]"),
        require_optional_dependency("google.protobuf", extra="protobuf"),
    ):
        raise ModuleNotFoundError("missing", name=missing)


def test_optional_import_helper_does_not_mistake_a_sibling_for_a_parent():
    from dubbo.utils import require_optional_dependency

    failure = ModuleNotFoundError("missing", name="google.proto")
    with (
        pytest.raises(ModuleNotFoundError, match="missing") as caught,
        require_optional_dependency("google.protobuf", extra="protobuf"),
    ):
        raise failure
    assert caught.value is failure
