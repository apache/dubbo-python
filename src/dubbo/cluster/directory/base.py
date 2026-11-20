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

import typing
from collections.abc import Sequence

from dubbo.extension import Resource
from dubbo.rpc.invocation import Invocation, Invoker

__all__ = ["Directory"]


class Directory(Resource, typing.Protocol):
    """The invokers of the providers a reference may call, which its cluster asks for on every attempt.

    It owns the invokers it holds: closing it closes them.
    """

    @property
    def available(self) -> bool:
        """Whether one of its invokers is available."""
        ...

    def candidates(self, invocation: Invocation) -> Sequence[Invoker]:
        """Return the invokers ``invocation`` may go to now, possibly none.

        While they do not change, the same sequence object is returned.
        """
        ...
