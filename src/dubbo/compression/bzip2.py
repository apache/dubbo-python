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

import bz2

from dubbo.url import URL

from .base import Compressor, bounded_decompress

__all__ = ["Bzip2Compressor"]


class Bzip2Compressor(Compressor):
    """Compress messages in the bzip2 format."""

    def __init__(self, url: URL) -> None:
        pass

    def compress(self, data: bytes) -> bytes:
        return bz2.compress(data)

    def decompress(self, data: bytes, max_length: int) -> bytes:
        return bounded_decompress(bz2.BZ2Decompressor(), data, max_length)
