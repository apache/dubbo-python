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
import inspect
import sys
from dataclasses import dataclass
from typing import Any

from dubbo.compressor.compression import Compression
from dubbo.logger import LoggerAdapter
from dubbo.protocol.protocol import Protocol
from dubbo.remoting.transporter import Transporter


@dataclass
class ExtendedRegistry:
    """
    A dataclass to represent an extended registry.
    Attributes:
        interface: Any -> The interface of the registry.
        impls: dict[str, Any] -> A dict of implementations of the interface. -> {name: impl}
    """

    interface: Any
    impls: dict[str, Any]


"""Protocol registry."""
protocolRegistry = ExtendedRegistry(
    interface=Protocol,
    impls={
        "tri": "dubbo.protocol.triple.tri_protocol.TripleProtocol",
    },
)

"""Compression registry."""
compressionRegistry = ExtendedRegistry(
    interface=Compression,
    impls={
        "gzip": "dubbo.compressor.gzip_compression.GzipCompression",
    },
)


"""Transporter registry."""
transporterRegistry = ExtendedRegistry(
    interface=Transporter,
    impls={
        "aio": "dubbo.remoting.aio.aio_transporter.AioTransporter",
    },
)


"""LoggerAdapter registry."""
loggerAdapterRegistry = ExtendedRegistry(
    interface=LoggerAdapter,
    impls={
        "logging": "dubbo.logger.logging.logger_adapter.LoggingLoggerAdapter",
    },
)


def get_all_extended_registry() -> dict[Any, dict[str, Any]]:
    """
    Get all extended registries in the current module.
    :return: A dict of all extended registries. -> {interface: {name: impl}}
    """
    current_module = sys.modules[__name__]
    registries: dict[Any, dict[str, Any]] = {}
    for name, obj in inspect.getmembers(current_module):
        if isinstance(obj, ExtendedRegistry):
            registries[obj.interface] = obj.impls
    return registries
