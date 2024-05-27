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

import abc


class Compression(abc.ABC):
    """Compression interface."""

    def compress(self, data: bytes) -> bytes:
        """
        Compress data.
        :param data: data to be compressed.
        :return: compressed data.
        """
        raise NotImplementedError("Method 'compress' is not implemented.")

    def decompress(self, data: bytes) -> bytes:
        """
        Decompress data.
        :param data: data to be decompressed.
        :return: decompressed data.
        """
        raise NotImplementedError("Method 'decompress' is not implemented.")
