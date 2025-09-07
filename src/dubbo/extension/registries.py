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

from dataclasses import dataclass
from typing import Any

from dubbo.cluster import LoadBalance
from dubbo.codec import Codec
from dubbo.codec.json_codec import TypeHandler
from dubbo.codec.protobuf_codec import ProtobufEncoder
from dubbo.compression import Compressor, Decompressor
from dubbo.protocol import Protocol
from dubbo.registry import RegistryFactory
from dubbo.remoting import Transporter


@dataclass
class ExtendedRegistry:
    """
    A dataclass to represent an extended registry.

    :param interface: The interface of the registry.
    :type interface: Any
    :param impls: The implementations of the registry.
    :type impls: Dict[str, Any]
    """

    interface: Any
    impls: dict[str, Any]


# All Extension Registries
registries = [
    "registryFactoryRegistry",
    "loadBalanceRegistry",
    "protocolRegistry",
    "compressorRegistry",
    "decompressorRegistry",
    "transporterRegistry",
    "codecRegistry",
    "jsonTypeHandlerRegistry",
    "protoHandlerRegistry",
]

# RegistryFactory registry
registryFactoryRegistry = ExtendedRegistry(
    interface=RegistryFactory,
    impls={
        "zookeeper": "dubbo.registry.zookeeper.zk_registry.ZookeeperRegistryFactory",
    },
)

# LoadBalance registry
loadBalanceRegistry = ExtendedRegistry(
    interface=LoadBalance,
    impls={
        "random": "dubbo.cluster.loadbalances.RandomLoadBalance",
        "cpu": "dubbo.cluster.loadbalances.CpuLoadBalance",
    },
)

# Protocol registry
protocolRegistry = ExtendedRegistry(
    interface=Protocol,
    impls={
        "tri": "dubbo.protocol.triple.protocol.TripleProtocol",
    },
)

# Compressor registry
compressorRegistry = ExtendedRegistry(
    interface=Compressor,
    impls={
        "identity": "dubbo.compression.Identity",
        "gzip": "dubbo.compression.Gzip",
        "bzip2": "dubbo.compression.Bzip2",
    },
)

# Decompressor registry
decompressorRegistry = ExtendedRegistry(
    interface=Decompressor,
    impls={
        "identity": "dubbo.compression.Identity",
        "gzip": "dubbo.compression.Gzip",
        "bzip2": "dubbo.compression.Bzip2",
    },
)

# Transporter registry
transporterRegistry = ExtendedRegistry(
    interface=Transporter,
    impls={
        "aio": "dubbo.remoting.aio.aio_transporter.AioTransporter",
    },
)

# Codec registry
codecRegistry = ExtendedRegistry(
    interface=Codec,
    impls={
        "json": "dubbo.codec.json_codec.JsonTransportCodec",
        "protobuf": "dubbo.codec.protobuf_codec.ProtobufTransportCodec",
    },
)

# Protobuf handler registry
protoHandlerRegistry = ExtendedRegistry(
    interface=ProtobufEncoder,
    impls={
        "betterproto": "dubbo.codec.protobuf_codec.BetterprotoMessageHandler",
        "primitive": "dubbo.codec.protobuf_codec.PrimitiveHandler",
        "googleproto": "dubbo.codec.protobuf_codec.GoogleProtobufMessageHandler",
    },
)

# JSON type handler registry
jsonTypeHandlerRegistry = ExtendedRegistry(
    interface=TypeHandler,
    impls={
        "datetime": "dubbo.codec.json_codec.DateTimeHandler",
        "decimal": "dubbo.codec.json_codec.DecimalHandler",
        "collection": "dubbo.codec.json_codec.CollectionHandler",
        "enum": "dubbo.codec.json_codec.EnumHandler",
        "dataclass": "dubbo.codec.json_codec.DataclassHandler",
        "simple": "dubbo.codec.json_codec.SimpleTypesHandler",
        "pydantic": "dubbo.codec.json_codec.PydanticHandler",
    },
)
