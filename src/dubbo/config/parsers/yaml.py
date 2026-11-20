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

from collections.abc import Hashable, Mapping
from typing import cast

from dubbo.config.data import ConfigData
from dubbo.config.exceptions import ConfigParseError
from dubbo.utils import require_optional_dependency

with require_optional_dependency("yaml", extra="yaml"):
    import yaml
    from yaml.error import Mark
    from yaml.nodes import CollectionNode, MappingNode, Node

from .base import ConfigParser

__all__ = ["YamlParser"]


# The most nodes that aliases may add to a document, each standing for a copy of what it names.
_MAX_ALIASED_NODES = 10_000


class YamlParser(ConfigParser):
    """Reads a YAML mapping with safe constructors and acyclic aliases."""

    def loads(self, text: str, /) -> ConfigData:
        loader = _ConfigLoader(text)
        try:
            node = loader.get_single_node()
            if node is not None:
                sizes: dict[Node, int] = {}
                if _expanded_size(node, sizes) - len(sizes) > _MAX_ALIASED_NODES:
                    raise ConfigParseError(f"YAML aliases add more than {_MAX_ALIASED_NODES} nodes")
            data = loader.construct_document(node) if node is not None else None
        except (yaml.YAMLError, RecursionError) as error:
            raise ConfigParseError("invalid YAML configuration") from error
        finally:
            loader.dispose()

        if not isinstance(data, Mapping):
            raise ConfigParseError("configuration must have a mapping at its root")
        return data


class _ConfigLoader(yaml.SafeLoader):
    def construct_object(self, node: Node, deep: bool = False) -> object:
        # Eager construction lets PyYAML reject cycles while preserving ordinary aliases.
        return super().construct_object(node, deep=True)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, object]:
        # YAML permits keys of any type; configuration paths require strings.
        mapping = super().construct_mapping(node, deep=deep)
        if any(not isinstance(key, str) for key in mapping):
            # Composed nodes carry their position.
            line = cast(Mark, node.start_mark).line + 1
            raise ConfigParseError(f"configuration keys must be strings, in the mapping at line {line}")
        return mapping


def _expanded_size(node: Node, sizes: dict[Node, int]) -> int:
    """Return the number of nodes ``node`` holds with each alias counted as a copy of its anchor."""
    if node in sizes:
        return sizes[node]

    # A cycle counts once here; construction rejects it.
    sizes[node] = 1
    if isinstance(node, MappingNode):
        children = [child for pair in node.value for child in pair]
    elif isinstance(node, CollectionNode):
        children = node.value
    else:
        children = []
    sizes[node] = 1 + sum(_expanded_size(child, sizes) for child in children)
    return sizes[node]
