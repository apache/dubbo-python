#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from abc import ABC, abstractmethod
from typing import (
    Any,
    Type,
    Optional,
    List,
    Dict,
    Set,
    Protocol,
    runtime_checkable,
    Union,
)
from dataclasses import dataclass, fields, is_dataclass, asdict
from datetime import datetime, date, time
from decimal import Decimal
from collections import namedtuple
from pathlib import Path
from uuid import UUID
from enum import Enum
import weakref

try:
    from pydantic import BaseModel

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


class SerializationException(Exception):
    """Exception raised during serialization"""
    pass

class DeserializationException(Exception):
    """Exception raised during deserialization"""
    pass

class CircularReferenceException(SerializationException):
    """Exception raised when circular references are detected"""
    pass

@dataclass(frozen=True)
class SerializationState:
    _visited_objects: Set[int] = None
    maximum_depth: int = 100
    current_depth: int = 0

    def __post_init__(self):
        if self._visited_objects is None:
            object.__setattr__(self, "_visited_objects", set())

    def validate_circular_reference(self, obj: Any) -> None:
        object_id = id(obj)
        if object_id in self._visited_objects:
            raise CircularReferenceException(
                f"Circular reference detected for {type(obj).__name__}"
            )
        if self.current_depth >= self.maximum_depth:
            raise SerializationException(
                f"Maximum serialization depth ({self.maximum_depth}) exceeded"
            )

    def create_child_state(self, obj: Any) -> "SerializationState":
        new_visited = self._visited_objects.copy()
        new_visited.add(id(obj))
        return SerializationState(
            _visited_objects=new_visited,
            maximum_depth=self.maximum_depth,
            current_depth=self.current_depth + 1,
        )


@runtime_checkable
class TypeSerializationProvider(Protocol):
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool: ...

    def serialize_to_dict(self, obj: Any, state: SerializationState) -> Any: ...


class TypeProviderRegistry:
    def __init__(self):
        self._type_cache: Dict[type, Optional[TypeSerializationProvider]] = {}
        self._providers: List[TypeSerializationProvider] = []
        self._weak_cache = weakref.WeakKeyDictionary()

    def register_provider(self, provider: TypeSerializationProvider) -> None:
        self._providers.append(provider)
        self._type_cache.clear()
        self._weak_cache.clear()

    def find_provider_for_object(self, obj: Any) -> Optional[TypeSerializationProvider]:
        obj_type = type(obj)
        if obj_type in self._type_cache:
            return self._type_cache[obj_type]
        provider = None
        for p in self._providers:
            if p.can_serialize_type(obj, obj_type):
                provider = p
                break
        self._type_cache[obj_type] = provider
        return provider


class DateTimeSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return obj_type in (datetime, date, time)

    def serialize_to_dict(
        self, obj: Union[datetime, date, time], state: SerializationState
    ) -> Dict[str, str]:
        if isinstance(obj, datetime):
            return {
                "__datetime__": obj.isoformat(),
                "__timezone__": str(obj.tzinfo) if obj.tzinfo else None,
            }
        elif isinstance(obj, date):
            return {"__date__": obj.isoformat()}
        else:
            return {"__time__": obj.isoformat()}


class DecimalSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return obj_type is Decimal

    def serialize_to_dict(
        self, obj: Decimal, state: SerializationState
    ) -> Dict[str, str]:
        return {"__decimal__": str(obj)}


class CollectionSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return obj_type in (set, frozenset)

    def serialize_to_dict(
        self, obj: Union[set, frozenset], state: SerializationState
    ) -> Dict[str, Any]:
        safe_items = []
        for item in obj:
            if isinstance(item, (str, int, float, bool, type(None))):
                safe_items.append(item)
            else:
                raise SerializationException(
                    f"Cannot serialize {type(item).__name__} in collection. "
                    f"Collections can only contain JSON-safe types (str, int, float, bool, None)"
                )
        return {
            "__frozenset__" if isinstance(obj, frozenset) else "__set__": safe_items
        }


class DataclassSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return is_dataclass(obj) and not isinstance(obj, type)

    def serialize_to_dict(self, obj: Any, state: SerializationState) -> Dict[str, Any]:
        state.validate_circular_reference(obj)
        try:
            field_data = asdict(obj)
            return {
                "__dataclass__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
                "__field_data__": field_data,
            }
        except (TypeError, RecursionError):
            field_data = {}
            for field in fields(obj):
                try:
                    field_data[field.name] = getattr(obj, field.name)
                except Exception as e:
                    raise SerializationException(
                        f"Cannot serialize field '{field.name}': {e}"
                    )
            return {
                "__dataclass__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
                "__field_data__": field_data,
            }


class NamedTupleSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return (
            hasattr(obj_type, "_fields")
            and hasattr(obj, "_asdict")
            and callable(obj._asdict)
        )

    def serialize_to_dict(self, obj: Any, state: SerializationState) -> Dict[str, Any]:
        return {
            "__namedtuple__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
            "__tuple_data__": obj._asdict(),
        }


class PydanticModelSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return HAS_PYDANTIC and isinstance(obj, BaseModel)

    def serialize_to_dict(
        self, obj: BaseModel, state: SerializationState
    ) -> Dict[str, Any]:
        state.validate_circular_reference(obj)
        if hasattr(obj, "model_dump"):
            model_data = obj.model_dump()
        else:
            model_data = obj.dict()
        return {
            "__pydantic_model__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
            "__model_data__": model_data,
        }


class SimpleTypeSerializationProvider:
    def can_serialize_type(self, obj: Any, obj_type: type) -> bool:
        return obj_type is UUID or isinstance(obj, (Path, Enum))

    def serialize_to_dict(
        self, obj: Union[UUID, Path, Enum], state: SerializationState
    ) -> Dict[str, str]:
        if isinstance(obj, UUID):
            return {"__uuid__": str(obj)}
        elif isinstance(obj, Path):
            return {"__path__": str(obj)}
        else:
            return {
                "__enum__": f"{obj.__class__.__module__}.{obj.__class__.__qualname__}",
                "__enum_value__": obj.value,
            }


class TypeProviderFactory:
    @staticmethod
    def create_default_registry() -> TypeProviderRegistry:
        registry = TypeProviderRegistry()
        default_providers = [
            DateTimeSerializationProvider(),
            DecimalSerializationProvider(),
            CollectionSerializationProvider(),
            DataclassSerializationProvider(),
            NamedTupleSerializationProvider(),
            PydanticModelSerializationProvider(),
            SimpleTypeSerializationProvider(),
        ]
        for provider in default_providers:
            registry.register_provider(provider)
        return registry

    @staticmethod
    def create_minimal_registry() -> TypeProviderRegistry:
        registry = TypeProviderRegistry()
        essential_providers = [
            DateTimeSerializationProvider(),
            DecimalSerializationProvider(),
            SimpleTypeSerializationProvider(),
        ]
        for provider in essential_providers:
            registry.register_provider(provider)
        return registry
