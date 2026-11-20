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

from collections.abc import Generator
from contextlib import contextmanager

__all__ = ["require_optional_dependency"]


@contextmanager
def require_optional_dependency(module: str, *, extra: str) -> Generator[None]:
    """Explain how to install a missing optional dependency.

    Only a missing ``module``, or a missing package that contains it, is
    reported; a dependency that fails to import one of its own modules is a
    broken installation and propagates.
    """
    try:
        yield
    except ModuleNotFoundError as error:
        # A broken dependency may itself import a missing module.
        if error.name is None or not f"{module}.".startswith(f"{error.name}."):
            raise
        raise ModuleNotFoundError(f"install apache-dubbo[{extra}] to use {module!r}", name=module) from error
