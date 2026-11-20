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

"""The kinds of type annotations that several readers of annotations take apart."""

import types
import typing

__all__ = ["TYPE_ALIASES", "UNIONS"]

# The aliases a type statement makes, from Python 3.12.
TYPE_ALIASES = tuple(alias for alias in (getattr(typing, "TypeAliasType", None),) if alias is not None)
# The origins of ``X | Y`` and ``Union[X, Y]``.
UNIONS = (typing.Union, types.UnionType)
