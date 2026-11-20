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

# The contract of the Java UserService, in Python: the names it has in Java,
# and Java types where Python ones would differ.

import dataclasses
import typing

import dubbo
import hessian2


# Hessian 2 carries an object under its Java class name, field by field; Java
# sees this class as org.apache.dubbo.samples.User. hessian2.Long is a Python
# int sent as a Java long, where an int would be sent as a Java int.
@hessian2.java_class("org.apache.dubbo.samples.User")
@dataclasses.dataclass
class User:
    id: hessian2.Long
    name: str
    email: str


@dubbo.service("org.apache.dubbo.samples.UserService")
class UserService(typing.Protocol):
    # The Java name of the method; Java also tells methods of one name apart
    # by the types of their parameters, here a long.
    @dubbo.method("getUser")
    async def get_user(self, id: hessian2.Long) -> User: ...
