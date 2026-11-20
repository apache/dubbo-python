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

from collections.abc import Mapping, Sequence
from typing import cast

__all__ = ["ConfigData", "insert_path", "merge"]

ConfigData = Mapping[str, object]


def merge(target: dict[str, object], incoming: ConfigData) -> None:
    """Merge ``incoming`` into ``target``: mappings merge, other values replace.

    Every mapping in ``target`` is created here, so sources are never modified.
    Lists and scalars are shared; nothing mutates them.
    """
    for key, value in incoming.items():
        if not isinstance(value, Mapping):
            target[key] = value
            continue

        section = target.get(key)
        if not isinstance(section, dict):
            section = target[key] = {}
        merge(cast(dict[str, object], section), cast(ConfigData, value))


def insert_path(root: dict[str, object], path: Sequence[str], value: object) -> None:
    """Set a nested value, rejecting empty segments and conflicting paths.

    A path conflicts when it repeats an earlier one or when one path would be
    both a value and a section, regardless of insertion order.
    """
    if not all(path):
        raise ValueError("empty path segment")

    current = root
    for segment in path[:-1]:
        child = current.setdefault(segment, {})
        if not isinstance(child, dict):
            raise ValueError("conflicting path")
        current = cast(dict[str, object], child)

    # This also catches two inputs that name the same path.
    if path[-1] in current:
        raise ValueError("conflicting path")
    current[path[-1]] = value
