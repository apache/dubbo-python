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

# The contract of the service: the server implements it, the client calls it.
# Both sides import this module, so they agree on the methods and their types.

import typing

import dubbo


# The name identifies the service on the wire and in registries. Java and Go
# services use the same kind of name, usually that of a Java interface.
@dubbo.service("org.apache.dubbo.samples.Greeter")
class Greeter(typing.Protocol):
    # Every method is async. Its type hints say what travels on the wire:
    # here a str goes in and a str comes back.
    async def greet(self, name: str) -> str: ...
