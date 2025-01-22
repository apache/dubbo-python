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

import gzip

from dubbo.compression import Compressor, Decompressor
from dubbo.loggers import loggerFactory

_LOGGER = loggerFactory.get_logger()
__all__ = ["Gzip"]


class Gzip(Compressor, Decompressor):
    """
    The GZIP compression and decompressor.
    """

    _MESSAGE_ENCODING = "gzip"

    @classmethod
    def get_message_encoding(cls) -> str:
        """
        Get message encoding of current compression
        :return: The message encoding.
        :rtype: str
        """
        return cls._MESSAGE_ENCODING

    def compress(self, data: bytes) -> bytes:
        """
        Compress the data.
        :param data: The data to compress.
        :type data: bytes
        :return: The compressed data.
        :rtype: bytes
        """
        try:
            return gzip.compress(data)
        except Exception as e:
            _LOGGER.error(f"Failed to compress data: {e}")
            raise

    def decompress(self, data: bytes) -> bytes:
        """
        Decompress the data.
        :param data: The data to decompress.
        :type data: bytes
        :return: The decompressed data.
        :rtype: bytes
        """
        try:
            return gzip.decompress(data)
        except Exception as e:
            _LOGGER.error(f"Failed to decompress data: {e}")
            raise
