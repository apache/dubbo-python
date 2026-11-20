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
from types import TracebackType
from typing import Self

__all__ = ["Resource"]


class Resource(typing.Protocol):
    """Something that holds resources, such as connections, until it is closed.

    It is ``anyio.abc.AsyncResource`` as a protocol, so that extension points
    can extend it.

    Implementations subclass it to get ``async with``, which closes the
    resource at the end of the block; one that opens on entering overrides
    ``__aenter__``.
    """

    async def aclose(self) -> None:
        """Release what the resource holds."""
        ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
