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
"""The descriptor pool of the protos the framework itself uses.

Their types are kept out of protobuf's default pool, where packages that
generate the same protos, such as googleapis-common-protos, register theirs.
"""

from dubbo.utils import require_optional_dependency

with require_optional_dependency("google.protobuf", extra="tri"):
    from google.protobuf import any_pb2, descriptor_pool, message_factory

__all__ = ["pool"]

pool = descriptor_pool.DescriptorPool()
# The well-known types the protos import, as the protobuf runtime describes them.
pool.AddSerializedFile(any_pb2.DESCRIPTOR.serialized_pb)
# The pure Python runtime builds the class of a message type only when asked, and fields of that type need it.
message_factory.GetMessageClass(pool.FindMessageTypeByName("google.protobuf.Any"))
